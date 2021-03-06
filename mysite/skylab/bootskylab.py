from __future__ import print_function
from __future__ import unicode_literals

import Queue  # queue for python 3
import importlib
import json
import logging
import logging.config
import math
import os
import pkgutil
import re
import threading
import time

from paramiko.ssh_exception import SSHException

import spur
from django.conf import settings
from django.db.models.signals import post_save
from skylab.signals import queue_task

import skylab.modules
from skylab.models import MPICluster, Task, ToolSet, ToolActivation, Tool


MAX_WAIT = settings.TRY_WHILE_NOT_EXIT_MAX_TIME

def setup_logging(
        path=os.path.dirname(os.path.abspath(__file__)) + '/logs/skylab_log_config.json',
        default_level=logging.INFO,

):
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

#todo: if task is created do not add queue toolset activation
#       instead, when task is about to be executed check if toolset is activated else activate

class MPIThreadManager(object):
    def __init__(self):
        self.threadHash = {}
        self.logger = logging.getLogger(__name__)
        clusters = MPICluster.objects.exclude(status=5)
        self.logger.info("Creating MPIThreads")
        self._connected_to_frontend = threading.Event()

        self.frontend_shell = None
        connect_to_frontend_thread = threading.Thread(target=self.connect_to_frontend)
        connect_to_frontend_thread.start()



        post_save.connect(receiver=self.receive_mpi_cluster_from_post_save_signal, sender=MPICluster,
                          dispatch_uid="receive_mpi_from_post_save_signal")
        # post_save.connect(receiver=self.receive_task_from_queue_task_signal, sender=Task,
        #                    dispatch_uid="receive_task_from_queue_task_signal")
        queue_task.connect(receiver=self.receive_task_from_queue_task_signal, sender=Task,
                           dispatch_uid="receive_task_from_queue_task_signal")

        # this may lead to duplicates on mpi create,
        # activate_toolset checks if the toolset is activated before execution
        post_save.connect(receiver=self.receive_toolactivation_from_post_save_signal, sender=ToolActivation,
                          dispatch_uid="receive_toolactivation_from_post_save_signal")


        for cluster in clusters:
            if cluster.id not in self.threadHash:
                t = MPIThread(cluster, self)
                self.threadHash[cluster.id] = t
                t.start()

        super(MPIThreadManager, self).__init__()

    def connect_to_frontend(self):
        if self.frontend_shell is None:
            self.frontend_shell = spur.SshShell(hostname=settings.FRONTEND_IP,
                                                username=settings.FRONTEND_USERNAME,
                                                password=settings.FRONTEND_PASSWORD,
                                                missing_host_key=spur.ssh.MissingHostKey.accept)
            retries = 0
            exit_loop = False
            while not exit_loop:
                try:
                    self.logger.info("Connecting to frontend...")
                    # check if connection is sucessful
                    # from : http://stackoverflow.com/questions/28288533/check-if-paramiko-ssh-connection-is-still-alive
                    channel = self.frontend_shell._get_ssh_transport().send_ignore()
                    self._connected_to_frontend.set()
                    self.logger.info("Connected to frontend...")
                    exit_loop = True  # exit loop

                except (spur.ssh.ConnectionError, EOFError) as e:
                    self.logger.error("Error connecting to frontend", exc_info=True)

                finally:
                    if not exit_loop:
                        retries += 1
                        wait_time = min(math.pow(2, retries), MAX_WAIT)
                        self.logger.debug('Waiting {0}s until next retry'.format(wait_time))
                        time.sleep(wait_time)
        return self.frontend_shell

    def get_frontend_shell(self):
        if not self._connected_to_frontend.isSet():
            self._connected_to_frontend.wait()
        return self.frontend_shell

    def receive_toolactivation_from_post_save_signal(self, sender, instance, created, **kwargs):
        if instance.status == 1:
            logging.info(
                'Received ToolActivation #{0} ({1}) for MPI #{2}'.format(instance.id, instance.toolset.display_name,
                                                                         instance.mpi_cluster_id))

            self.threadHash[instance.mpi_cluster_id].add_task_to_queue(1, "self.activate_tool({0})".format(
                instance.toolset_id))

    def receive_task_from_queue_task_signal(self, task_instance, **kwargs):
        logging.info('Received Task #{0} for MPI #{1}'.format(task_instance.id, task_instance.mpi_cluster.cluster_name))

        # append to queue
        self.threadHash[task_instance.mpi_cluster_id].add_task_to_queue(task_instance.priority, task_instance)

    def receive_mpi_cluster_from_post_save_signal(self, sender, instance, created, **kwargs):
        if created:
            t = MPIThread(instance, self)
            self.threadHash[instance.id] = t
            t.start()

class MPIThread(threading.Thread):
    def __init__(self, mpi_cluster, manager):
        # current implementation. task_queue only has a single consumer.

        """"
        This design can be improved and cater multiple consumers for this queue
        In multiple consumers, this thread would be the producer
        Consumers consume task queue, pass cluster_shell to consumer instances
        Recommendation: Dynamic consumers spawn based on task intensity
        If current task is light on resources regardless of expected running time,
        A new consumer is signalled that it is allowed to consume
        """
        self.task_queue = Queue.PriorityQueue()

        self._stop = threading.Event()
        self._ready = threading.Event()
        self.manager = manager
        self.mpi_cluster = mpi_cluster
        self.frontend_shell = None
        self.cluster_shell = None
        self.logger = logging.getLogger(__name__)
        self.log_prefix = 'MPI [id:{0},name:{1}] : '.format(self.mpi_cluster.id, self.mpi_cluster.cluster_name)

        self.logger.info(self.log_prefix + 'Spawned MPI Thread')

        init_thread = threading.Thread(target=self.connect_or_create)
        init_thread.start()  # sets event _connection on finish
        super(MPIThread, self).__init__()

    def connect_or_create(self):
        if self.mpi_cluster.status == 0:  # create
            self.create_mpi_cluster()
        else:
            self.mpi_cluster.change_status(1)

        self.connect_to_cluster(init=True)  #get working cluster shell

        if self.mpi_cluster.status == 0:  # create
            self.install_dependencies()  #zip
            self.mpi_cluster.change_status(1)

        self.mpi_cluster.change_status(2)  # cluster available
        self._ready.set()

    def connect_to_cluster(self,init=False):
        self.cluster_shell = spur.SshShell(hostname=self.mpi_cluster.cluster_ip, username=settings.CLUSTER_USERNAME,
                                           password=settings.CLUSTER_PASSWORD,
                                           missing_host_key=spur.ssh.MissingHostKey.accept)
        self.test_cluster_connection(init=init)

        # fix for unresponsive ssh from srg.ics
        self.logger.debug(self.log_prefix + 'Set mtu to 1454')
        command = "sudo ifconfig eth0 mtu 1454"
        ssh_fix = self.cluster_shell.spawn(["sh", "-c", command], use_pty=True)
        ssh_fix.stdin_write(settings.CLUSTER_PASSWORD + "\n")
        ssh_fix.wait_for_result()


        # when instance is restarted this settings resets : observation >> confirmed
        self.logger.debug(self.log_prefix + 'Set kernel.shmmax=500000000')
        command = 'sudo /sbin/sysctl -w kernel.shmmax=500000000'
        shmax_fixer = self.cluster_shell.spawn(['sh', '-c', command], use_pty=True)
        shmax_fixer.stdin_write(settings.CLUSTER_PASSWORD + "\n")
        shmax_fixer.wait_for_result()


    def test_cluster_connection(self, init=False):
        retries = 0
        exit_loop = False
        while not exit_loop:
            try:
                self.logger.info(self.log_prefix + "Testing connection to cluster...")
                # check if connection is sucessful
                # from : http://stackoverflow.com/questions/28288533/check-if-paramiko-ssh-connection-is-still-alive
                channel = self.cluster_shell._get_ssh_transport().send_ignore()
                exit_loop = True  # exit loop

            except (spur.ssh.ConnectionError, EOFError) as e:
                self.logger.error(self.log_prefix + "Error connecting to cluster", exc_info=True)
                self.mpi_cluster.change_status(4)

            finally:
                if not exit_loop:
                    retries += 1
                    wait_time = min(math.pow(2, retries), MAX_WAIT)
                    self.logger.debug('Waiting {0}s until next retry'.format(wait_time))
                    time.sleep(wait_time)

        self.logger.info(self.log_prefix + "Connected to cluster...")
        if not init:
            self.mpi_cluster.change_status(2)

    def install_dependencies(self):
        retries = 0
        exit_loop = False
        while not exit_loop:


            try:
                # update p2c-tools
                self.logger.debug(self.log_prefix + "Updating p2c-tools")
                command = "rm p2c-tools*"
                self.cluster_shell.run(["sh", "-c", command])

                self.cluster_shell.run(["wget", "10.0.3.10/downloads/p2c/p2c-tools"])
                self.cluster_shell.run(["chmod", "755", "p2c-tools"])
                p2c_updater = self.cluster_shell.spawn(["./p2c-tools"], use_pty=True)
                p2c_updater.stdin_write(settings.CLUSTER_PASSWORD + "\n")
                self.logger.debug(self.log_prefix + p2c_updater.wait_for_result().output)
                self.logger.debug(self.log_prefix + self.cluster_shell.run(["p2c-tools"]).output)
                self.logger.debug(self.log_prefix + "Updated p2c-tools")

                # sudo apt-get update
                self.logger.debug(self.log_prefix + "Updating apt-get")
                command = "sudo apt-get update"
                apt_get_update_shell = self.cluster_shell.spawn(["sh", "-c", command], use_pty=True)
                apt_get_update_shell.stdin_write(settings.CLUSTER_PASSWORD + "\n")
                self.logger.debug(self.log_prefix + apt_get_update_shell.wait_for_result().output)
                self.logger.debug(self.log_prefix + "Updated apt-get")

                # install zip
                self.logger.debug(self.log_prefix + "Installing zip")
                command = "sudo apt-get install zip -y"
                zip_shell = self.cluster_shell.spawn(["sh", "-c", command], use_pty=True)
                time.sleep(1)
                zip_shell.stdin_write(settings.CLUSTER_PASSWORD + "\n")
                # zip_shell.stdin_write("Y\n")
                self.logger.debug(self.log_prefix + zip_shell.wait_for_result().output)
                self.logger.debug(self.log_prefix + "Installed zip")
                exit_loop = True  # exit loop

            except spur.RunProcessError as err:
                # run process error with return code -1 (no value returned) is returned during unresponsive connection
                if err.return_code == -1:  # no return code received
                    self.logger.error(
                        self.log_prefix + 'No response from server. Retrying command ({0})'.format(command))
                else:
                    self.logger.error(self.log_prefix + 'RuntimeError: ' + err.message)

            except spur.ssh.ConnectionError:
                self.logger.error(self.log_prefix + "Connection Error to MPI Cluster", exc_info=True)

            finally:
                if not exit_loop:
                    retries += 1
                    wait_time = min(math.pow(2, retries), MAX_WAIT)
                    self.logger.debug('Waiting {0}s until next retry'.format(wait_time))
                    time.sleep(wait_time)

    def activate_toolset(self, toolset_id):
        # check if toolset is already activated
        tool_activation_instance = ToolActivation.objects.get(toolset=toolset_id, mpi_cluster=self.mpi_cluster.id)
        if not tool_activation_instance.status == 2:
            toolset = ToolSet.objects.get(pk=toolset_id)

            self.logger.debug(self.log_prefix + "Activating " + toolset.display_name)
            retries = 0
            exit_loop = False
            while not exit_loop:
                # if toolset.p2ctool_name == 'quantum-espresso':
                #     pass
                #     #todo : host in p2c webserver
                #     # command = 'wget http://qe-forge.org/gf/download/frsrelease/211/968/espresso-5.4.0.tar.gz &&' \
                #     #           'tar -xvsf espresso-5.4.0.tar.gz && cd espresso-5.4.0/  &&  ./configure  &&' \
                #     #           'make all'
                # else:
                command = "p2c-tools activate {0}".format(toolset.p2ctool_name)
                try:
                    tool_activator = self.cluster_shell.spawn(["sh", "-c", command], use_pty=True)
                    tool_activator.stdin_write(settings.CLUSTER_PASSWORD + "\n")
                    tool_activator.wait_for_result()
                    self.logger.info(self.log_prefix + u"{0:s} is now activated.".format(toolset.display_name))
                    self.logger.debug(u"{0:s}{1:s}".format(self.log_prefix ,tool_activator.wait_for_result().decode('utf-8')))

                    # set activated to true after installation
                    tool_activation_instance.refresh_from_db()
                    tool_activation_instance.status = 2
                    tool_activation_instance.save()

                    exit_loop = True  #exit loop
                except spur.RunProcessError as err:
                    if err.return_code == -1:  # no return code received
                        self.logger.error(
                            self.log_prefix + "No response from server. Command: ({0})".format(command),
                            exc_info=True)
                    else:
                        self.logger.error(self.log_prefix + 'RuntimeError: ' + err.message)

                except spur.ssh.ConnectionError:
                    self.logger.error(self.log_prefix + "Connection Error to MPI Cluster", exc_info=True)

                finally:
                    if not exit_loop:
                        retries += 1
                        wait_time = min(math.pow(2, retries), MAX_WAIT)
                        self.logger.debug('Waiting {0}s until next retry'.format(wait_time))
                        time.sleep(wait_time)

    def create_mpi_cluster(self):
        self.logger.info(self.log_prefix + "Creating MPI Cluster")
        self.frontend_shell = self.manager.get_frontend_shell()  # get working frontend_shell
        retries = 0
        exit_loop = False
        while not exit_loop:
            command = "./vcluster-stop {0} {1}".format(self.mpi_cluster.cluster_name, self.mpi_cluster.cluster_size)
            try:
                self.logger.debug(self.log_prefix + "Execute " + command)
                self.frontend_shell.run(["sh", "-c", command], cwd="vcluster")
                # self.frontend_shell.run(["./vcluster-stop", self.mpi_cluster.cluster_name, str(self.mpi_cluster.cluster_size)],
                #                         cwd="vcluster")  # to remove duplicates in case server restart while creating

                command = "./vcluster-start {0} {1}".format(self.mpi_cluster.cluster_name,
                                                            self.mpi_cluster.cluster_size)
                self.logger.debug(self.log_prefix + "Execute " + command)
                result_cluster_ip = self.frontend_shell.run(["sh", "-c", command], cwd="vcluster")

                exit_loop = True  # exit loop
            except spur.RunProcessError as err:
                if err.return_code == -1:  # no return code received
                    self.logger.error(
                        self.log_prefix + "No response from server. Command: ({0})".format(command),
                        exc_info=True)
                else:
                    self.logger.error(self.log_prefix + 'RuntimeError: ' + err.message)

            except spur.ssh.ConnectionError:
                self.logger.error(self.log_prefix + "Connection Error to MPI Cluster", exc_info=True)
            finally:
                if not exit_loop:
                    retries += 1
                    wait_time = min(math.pow(2, retries), MAX_WAIT)
                    self.logger.debug('Waiting {0}s until next retry'.format(wait_time))
                    time.sleep(wait_time)

        self.logger.debug(self.log_prefix + result_cluster_ip.output)
        p = re.compile("(?P<username>\S+)@(?P<floating_ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
        m = p.search(result_cluster_ip.output)
        # self.cluster_username = m.group('username')
        # self.cluster_password = self.cluster_username
        cluster_ip = m.group('floating_ip')
        # print "%s@%s" % (self.cluster_username, self.cluster_ip)
        # self.print_to_console("Cluster ip: %s" % self.cluster_ip)
        self.mpi_cluster.refresh_from_db()
        self.mpi_cluster.cluster_ip = cluster_ip
        self.mpi_cluster.save()
        self.logger.debug(self.log_prefix + 'Obtained cluster ip: {0}'.format(cluster_ip))

    def run(self):
        self.logger.info(self.log_prefix + "Populating task queue")

        # get tasks that are not finished yet
        tasks = Task.objects.filter(mpi_cluster=self.mpi_cluster).exclude(status_code=200).exclude(
            status_code=401)#.order_by('priority', 'created')  # status 400 is not terminal, 401 is
        # lower priority value are prioritized

        for task in tasks:
            self.add_task_to_queue(task.priority, task)

        # get toolactivations queued for activation (status == 1)
        queued_toolset_activations = self.mpi_cluster.toolsets.filter(toolactivation__status=1)
        for toolset in queued_toolset_activations:
            self.add_task_to_queue(1, "self.activate_toolset({0})".format(toolset.id))
        self._ready.wait()  # block waiting for connected event to be set

        while not self._stop.isSet():

            self.logger.debug(self.log_prefix + 'Waiting 5 seconds, before processing again')
            event_is_set = self._stop.wait(5)

            # test cluster connection before processing
            self.test_cluster_connection()

            if event_is_set:
                self.logger.info(self.log_prefix + 'Terminating ...')
            else:
                try:
                    queue_obj = self.task_queue.get(block=True, timeout=60) #block wait for 60s, then raise exception

                    if queue_obj[0] == 1:  # p2c-tools activate are always priority # 1
                        self.logger.debug(self.log_prefix + "Running " + queue_obj[1])
                        exec (queue_obj[1])

                    elif isinstance(queue_obj[1], Task):
                        current_task = queue_obj[1]
                        current_task.refresh_from_db()  # refresh instance
                        task_log_prefix = '[Task {0} ({1})] : '.format(current_task.id, current_task.tool.display_name)
                        self.logger.info('{0}Processing {1}'.format(self.log_prefix, task_log_prefix))
                        mod = importlib.import_module('{0}.executables'.format(current_task.tool.toolset.package_name))

                        cls = getattr(mod, current_task.tool.executable_name)
                        executable_obj = cls(shell=self.cluster_shell, task=current_task, logger=self.logger,
                                             log_prefix=self.log_prefix + task_log_prefix)
                        try:
                            executable_obj.run_tool()
                        except SSHException:
                            current_task.refresh_from_db()
                            current_task.priority += 1
                            current_task.save()
                            self.logger.error(self.log_prefix + task_log_prefix + "SSH Connection dropped. Reconnecting to cluster and requeue task with lower priority.")
                            self.connect_to_cluster(init=False)
                            self.add_task_to_queue(current_task.priority, current_task)
                    self.task_queue.task_done()
                except Queue.Empty:
                    if self.mpi_cluster.queued_for_deletion:  # if queue is empty and cluster is queued for deletion
                        self._stop.set()
                        self.logger.info(self.log_prefix + "Deleting MPI Cluster")
                        self.frontend_shell = self.manager.get_frontend_shell()  # get working frontend_shell
                        retries = 0
                        exit_loop = False
                        while not exit_loop:
                            command = "./vcluster-stop {0} {1}".format(self.mpi_cluster.cluster_name,
                                                                       self.mpi_cluster.cluster_size)
                            try:
                                self.logger.debug(self.log_prefix + "Execute " + command)
                                self.frontend_shell.run(["sh", "-c", command], cwd="vcluster")
                                # self.frontend_shell.run(["./vcluster-stop", self.mpi_cluster.cluster_name,
                                # str(self.mpi_cluster.cluster_size)],
                                #                         cwd="vcluster")  # to remove duplicates in case server restart while creating
                                exit_loop = True  # exit loop

                            except spur.RunProcessError as err:
                                if err.return_code == -1:  # no return code received
                                    self.logger.error(
                                        self.log_prefix + 'No response from server. Retrying command ({0})'.format(
                                            command))
                                else:
                                    self.logger.error(self.log_prefix + 'RuntimeError: ' + err.message)

                            except spur.ssh.ConnectionError:
                                self.logger.error(self.log_prefix + "Connection Error to MPI Cluster", exc_info=True)

                            finally:
                                if not exit_loop:
                                    retries += 1
                                    wait_time = min(math.pow(2, retries), MAX_WAIT)
                                    self.logger.debug(self.log_prefix+'Waiting {0}s until next retry'.format(wait_time))
                                    time.sleep(wait_time)

                        self.logger.info(self.log_prefix + ' Cluster deleted')
                        self.mpi_cluster.cluster_name += ' (deleted)'
                        self.mpi_cluster.save()
                        self.mpi_cluster.toolsets.clear()  # clear toolsets, toolactivation
                        self.mpi_cluster.change_status(5)
                    else:
                        self.logger.debug(self.log_prefix+"Queue is empty. Sleeping for 30 seconds")
                        time.sleep(30) #sleep for 30 seconds before processing again, since queue is empty

    def add_task_to_queue(self, priority, task):
        self.task_queue.put((priority, task))
        if isinstance(task, Task):
            task.change_status(status_code=101, status_msg="Task queued")
            self.logger.debug(self.log_prefix + 'Queued task [id:{0},priority:{1}]'.format(task.id, priority))


def install_toolsets():  # searches for packages inside modules folder
    package = skylab.modules
    prefix = package.__name__ + "."
    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__, prefix):
        if ispkg:  # for packages
            submod_prefix = modname + "."
            pkg = importer.find_module(modname).load_module(modname)
            for submodimporter, submodname, submodispkg in pkgutil.iter_modules(pkg.__path__, submod_prefix):
                if submodname.endswith(".install"):
                    mod = submodimporter.find_module(submodname).load_module(submodname)
                    mod.insert_to_db()


def add_tools_to_toolset(tools, toolset):  # creates db entries for tools and associates them with toolset
    for t in tools:
        display_name = t.get('display_name')
        simple_name = t.get('simple_name', re.sub(r'[\s_/-]+', '', display_name.lower()))
        view_name = t.get('view_name', re.sub(r'[\s_/-]+', '', display_name.title()) + "View")  # convention format
        executable_name = t.get('executable_name', re.sub(r'[\s_/-]+', '', display_name.title()) + "Executable")
        # description = t.get("description", "No description provided")
        description = t.get("description", "No description provided")

        Tool.objects.update_or_create(simple_name=simple_name,
                                      defaults={
                                          'display_name': display_name,
                                          'executable_name': executable_name,
                                          'view_name': view_name,
                                          'description': description,
                                          'toolset': toolset

                                      })
