from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field
from django import forms
from django.db.models import Q
from multiupload.fields import MultiFileField

from skylab.models import MPI_Cluster


class SelectMPIFilesForm(forms.Form):


    def __init__(self, *args, **kwargs):
        self.user = kwargs.get('user')
        super(SelectMPIFilesForm, self).__init__(*args, **kwargs)
        # self.fields['mpi_cluster'].queryset = MPI_Cluster.objects.filter(creator=self.user)
        current_user_as_creator = Q(creator=self.user)
        cluster_is_public = Q(shared_to_public=True)
        supports_gamess = Q(supported_tools="gamess")
        # is_ready = Q(status=1)
        q = MPI_Cluster.objects.filter(current_user_as_creator | cluster_is_public)
        q = q.filter(supports_gamess).exclude(status=4) #exclude unusable clusters

        self.fields['mpi_cluster'] = forms.ModelChoiceField(queryset=q)

        self.helper = FormHelper()
        self.helper.form_tag = False
        # self.helper.form_id = 'id-rayForm'
        # self.helper.form_class = 'use-tool-forms'
        # self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(    #crispy_forms layout

            Div(
                Field('mpi_cluster', wrapper_class='col-xs-4'),
                css_class="col-sm-12"
            ),


        )


def validate_ray_file_extension(value):
    # export.txt, qseq.txt are not supported because of lack of documentation on their use case
    valid_file_extensions = ['.fasta', '.fa', '.fasta.gz', '.fa.gz', '.fasta.bz2', '.fa.bz2', '.fastq', '.fq',
                             '.fastq.gz', '.fq.gz', '.fastq.bz2',
                             '.fq.bz2', '.sff', '.csfasta', '.csfa', '.conf'
                             ]
    valid = False
    for ext in valid_file_extensions:
        if value.name.lower().endswith(ext):
            valid = True
            break
    if not valid:
        raise forms.ValidationError(u'Filetype not supported', code='invalid_filetype')


class InputParameterForm(forms.Form):
    PARAMETER_CHOICES = (   #input parameter args
                        ('-p','-p'),
                        ('-i','-i'),
                        ('-s','-s'),
    )
    parameter = forms.ChoiceField(choices=PARAMETER_CHOICES)
    avg_outer_distance = forms.DecimalField(label="Average outer distance", required=False, help_text="Optional.",
                                            min_value=0)
    std_deviation = forms.DecimalField(label="Standard deviation", required=False, help_text="Optional.", min_value=0)

    input_file1 = forms.FileField(label="Input file 1", validators=[validate_ray_file_extension], required=False)
    input_file2 = forms.FileField(label="Input file 2", validators=[validate_ray_file_extension], required=False)


    def __init__(self, *args, **kwargs):
        super(InputParameterForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.disable_csrf = True
        self.helper.form_tag = False  # remove form headers
        # self.helper.form_error_title = "Form Errors"
        # self.helper.form_id = 'id-rayForm'
        # self.helper.form_class = 'use-tool-forms'
        # self.helper.form_method = 'post'

        self.helper.form_action = ''

        self.helper.layout = Layout(  # layout using crispy_forms
            Div(
                Div(Field('parameter', css_class='parameter'), css_class='col-xs-1'),
                Div('avg_outer_distance', css_class='col-xs-2'),
                Div('std_deviation', css_class='col-xs-2'),

                Div('input_file1', css_class='col-xs-3'),
                Div('input_file2', css_class='col-xs-3'),

                css_class='row-fluid col-sm-12 form-container'
            ),
        )

    def clean(self):
        if self.cleaned_data:
            parameter = self.cleaned_data['parameter']
            input_file1 = self.cleaned_data.get('input_file1')
            input_file2 = self.cleaned_data.get('input_file2')

            # print parameter, input_file1

            if parameter == '-p':  # -p needs two input files

                if not input_file1 or not input_file2:
                    raise forms.ValidationError(
                        '-p parameter requires two input files',
                        code='-p_incomplete_input_files'
                    )

            elif parameter == '-i' or parameter == '-s':  # -i and -s needs one input file
                if not input_file1:
                    raise forms.ValidationError(
                        '%s parameter requires one input file' % parameter,
                        code='%s_incomplete_input_files' % parameter
                    )


def odd_number_validator(value):
    if (value % 2 == 0):
        raise forms.ValidationError(u'Value must be odd', code='kmer_even_input')


def tsv_file_validator(file):
    pass


class OtherParameterForm(forms.Form):
    param_kmer = forms.BooleanField(initial=False, required=False)
    # todo: verify min_value for kmer_length, 32 is default max if not specified in compilation
    # source: http://blog.gmane.org/gmane.science.biology.ray-genome-assembler/month=20121101
    subparam_kmer_length = forms.IntegerField(initial=21, validators=[odd_number_validator], max_value=32, min_value=1,
                                              required=False)

    # Ray surveyor options
    param_run_surveyor = forms.BooleanField(initial=False, required=False)
    param_read_sample_graph = forms.BooleanField(initial=False, required=False)  # dependent on -write-kmers parameter
    # sampleName = tool_activity_%d % id, sampleGraphFile = output_directory/kmers.txt

    # Assembly options are skipped because documentation says (defaults work well)
    # Distributed storage engine options are skipped due to lack of knowledge with mpi ranks

    # Biological abundances
    param_search = forms.BooleanField(initial=False, required=False)
    subparam_searchFiles = MultiFileField(min_num=1, required=False,
                                          help_text="Provide fasta files to be searched in the de Bruijn graph.")  # save to tool_activity_x/input/search
    param_one_color_per_file = forms.BooleanField(initial=False, required=False)

    # Taxonomic profiling with colored de Bruijn graphs
    param_with_taxonomy = forms.BooleanField(required=False, initial=False)
    subparam_genome_to_taxon_file = forms.FileField(required=False, initial=False)
