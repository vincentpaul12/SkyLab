from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, Fieldset, HTML, Submit
from crispy_forms.bootstrap import AppendedText, Tab, TabHolder
from multiupload.fields import MultiFileField
from validators import pdbqt_file_extension_validator, dpf_file_extension_validator, gpf_file_extension_validator
from skylab.models import MPI_Cluster
from django.db.models import Q
from django.core.validators import MinValueValidator, MaxValueValidator
from skylab.modules.base_tool import MPIModelChoiceField


class AutodockForm(forms.Form):
    # + ligand .pdbqt + receptor.pdbqt
    param_receptor_file = forms.FileField(label="Receptor", help_text="(.pdbqt)",
                                          validators=[pdbqt_file_extension_validator])
    param_ligand_file = forms.FileField(label="Ligand", help_text="(.pdbqt)",
                                        validators=[pdbqt_file_extension_validator])
    param_dpf_file = forms.FileField(label="Dock parameter", help_text="(.dpf)",
                                     validators=[dpf_file_extension_validator])  # .dpf file
    param_dlg_filename = forms.CharField(required=False, label="Log filename", help_text="default: dpf_filename.dlg",
                                         widget=forms.TextInput(attrs={
                                             'placeholder': 'filename'}))  # default: dpf_filename.dlg   can be ommitted
    param_k = forms.BooleanField(required=False, label="-k", help_text="Keep original residue numbers")
    param_i = forms.BooleanField(required=False, label="-i", help_text="Ignore header-checking")
    param_t = forms.BooleanField(required=False, label="-t",
                                 help_text="Parse the PDBQT file to check torsions, then stop.")
    param_d = forms.BooleanField(required=False, label="-d", help_text="Increment debug level")


    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(AutodockForm, self).__init__(*args, **kwargs)

        current_user_as_creator = Q(creator=self.user)
        cluster_is_public = Q(shared_to_public=True)
        supports_autodock = Q(supported_tools="autodock")
        # is_ready = Q(status=1)
        q = MPI_Cluster.objects.filter(current_user_as_creator | cluster_is_public)
        q = q.filter(supports_autodock).exclude(status=4)  # exclude unusable clusters

        self.fields['mpi_cluster'] = MPIModelChoiceField(queryset=q, label="MPI Cluster",
                                                         help_text="Getting an empty list? Try <a href='../create_mpi_cluster'>creating an MPI Cluster</a> first.")

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field('mpi_cluster', wrapper_class='col-xs-5'),
                css_class="col-sm-12"
            ),
            Fieldset(
                'Input',
                Div(
                    Div('param_receptor_file', css_class='col-xs-4'),
                    Div('param_ligand_file', css_class='col-xs-4'),
                    Div('param_dpf_file', css_class='col-xs-4'),
                    css_class='row-fluid col-sm-12'
                )
            ),
            Fieldset(
                'Output',
                Div(
                    Div(AppendedText('param_dlg_filename', '.dlg'), css_class='col-xs-4'),
                    css_class='row-fluid col-sm-12'
                ),
            ),
            Fieldset(
                'Other parameters',
                # Div(
                #     Div(AppendedText('param_dlg_filename', '.dlg'),css_class='col-xs-4'),
                #     css_class='row-fluid col-sm-12'
                # ),
                Div(
                    Div('param_k', css_class="col-xs-4"),
                    Div('param_i', css_class="col-xs-4"),
                    Div('param_t', css_class="col-xs-4"),
                    Div('param_d', css_class="col-xs-4"),
                    css_class='row-fluid col-sm-12'
                )
            ),
        )



class AutogridForm(forms.Form):
    param_receptor_file = forms.FileField(label="Receptor", help_text="(.pdbqt)",
                                          validators=[pdbqt_file_extension_validator])
    param_ligand_file = forms.FileField(label="Ligand", help_text="(.pdbqt)",
                                        validators=[pdbqt_file_extension_validator])
    param_gpf_file = forms.FileField(label="Grid parameter", help_text="(.gpf)",
                                     validators=[gpf_file_extension_validator])
    param_glg_filename = forms.CharField(required=False, help_text="default: gpf_filename.glg",
                                         widget=forms.TextInput(attrs={'placeholder': 'filename'}))
    param_d = forms.BooleanField(required=False, label="-d", help_text="Increment debug level")
    param_use_with_autodock = forms.BooleanField(required=False, label='Use with AutoDock')

    param_dpf_file = forms.FileField(required=False, label="Dock parameter", help_text="(.dpf)",
                                     validators=[dpf_file_extension_validator])  # .dpf file

    param_dlg_filename = forms.CharField(required=False, label="Log filename", help_text="default: dpf_filename.dlg",
                                         widget=forms.TextInput(attrs={
                                             'placeholder': 'filename'}))  # default: dpf_filename.dlg   can be ommitted
    param_k = forms.BooleanField(required=False, label="-k", help_text="Keep original residue numbers")
    param_i = forms.BooleanField(required=False, label="-i", help_text="Ignore header-checking")
    param_t = forms.BooleanField(required=False, label="-t",
                                 help_text="Parse the PDBQT file to check torsions, then stop.")
    param_d_dock = forms.BooleanField(required=False, label="-d", help_text="Increment debug level")

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(AutogridForm, self).__init__(*args, **kwargs)

        current_user_as_creator = Q(creator=self.user)
        cluster_is_public = Q(shared_to_public=True)
        supports_autodock = Q(supported_tools="autodock")
        # is_ready = Q(status=1)
        q = MPI_Cluster.objects.filter(current_user_as_creator | cluster_is_public)
        q = q.filter(supports_autodock).exclude(status=4)  # exclude unusable clusters

        self.fields['mpi_cluster'] = MPIModelChoiceField(queryset=q, label="MPI Cluster",
                                                         help_text="Getting an empty list? Try <a href='../create_mpi_cluster'>creating an MPI Cluster</a> first.")

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'AutoGrid4',
                    Div(
                        Field('mpi_cluster', wrapper_class='col-xs-5'),
                        Div('param_use_with_autodock', css_class='col-xs-4 col-xs-offset-1'),
                        css_class="col-sm-12"
                    ),
                    Fieldset(
                        'Input',
                        Div(
                            Div('param_receptor_file', css_class='col-xs-4'),
                            Div('param_ligand_file', css_class='col-xs-4'),
                            Div('param_gpf_file', css_class='col-xs-4'),
                            css_class='row-fluid col-sm-12'
                        )
                    ),
                    Fieldset(
                        'Output',
                        Div(
                            Div(AppendedText('param_glg_filename', '.glg'), css_class='col-xs-4'),
                            css_class='row-fluid col-sm-12'
                        ),
                    ),
                    Fieldset(
                        'Other parameters',
                        Div(
                            Div('param_d', css_class='col-xs-4'),

                            css_class='col-sm-12'
                        )
                    ),
                ),
                Tab(
                    'AutoDock4',
                    Fieldset(
                        'Input',
                        Div(
                            Div('param_dpf_file', css_class='col-xs-4'),
                            css_class='row-fluid col-sm-12'
                        )
                    ),
                    Fieldset(
                        'Output',
                        Div(
                            Div(AppendedText('param_dlg_filename', '.dlg'), css_class='col-xs-4'),
                            css_class='row-fluid col-sm-12'
                        ),
                    ),
                    Fieldset(
                        'Other parameters',
                        Div(
                            Div('param_k', css_class="col-xs-4"),
                            Div('param_i', css_class="col-xs-4"),
                            Div('param_t', css_class="col-xs-4"),
                            Div('param_d_dock', css_class="col-xs-4"),
                            css_class='row-fluid col-sm-12'
                        )
                    ),

                )
            )
        )

        def clean(self):
            # todo: check checkbox
            pass
