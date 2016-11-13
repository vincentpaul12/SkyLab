from crispy_forms.bootstrap import AppendedText, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, Fieldset
from django import forms
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.text import get_valid_filename
from multiupload.fields import MultiFileField

from skylab.forms import MPIModelChoiceField, get_mpi_queryset_all
from skylab.models import MPICluster, ToolSet
from validators import pdbqt_file_extension_validator, dpf_file_extension_validator, gpf_file_extension_validator, \
    multi_grid_map_file_validator, dat_file_extension_validator


class Autodock4Form(forms.Form):
    # + ligand .pdbqt + receptor.pdbqt
    # param_receptor_file = forms.FileField(label="Receptor", help_text="(.pdbqt)",
    #                                       validators=[pdbqt_file_extension_validator])
    param_ligand_file = forms.FileField(label="Ligand file", help_text="File type: (.pdbqt)",
                                        validators=[pdbqt_file_extension_validator])
    param_dpf_file = forms.FileField(label="Dock parameter file", help_text="File type: (.dpf)",
                                     validators=[dpf_file_extension_validator])  # .dpf file
    param_grid_files = MultiFileField(min_num=1, validators=[multi_grid_map_file_validator], label="Grid map files",
                                      help_text="Files generated by autogrid (.map, .fld, .xyz)")  # .map, .fld, .xyz
    # param_dat_file = forms.FileField(required=False, label="Parameter library file", help_text="(.dat)",
    #                                  validators=[dat_file_extension_validator])  # .dat file
    param_dlg_filename = forms.CharField(required=False, label="Log filename", help_text="If specified, the output file will be named at [dlg_filename].dlg",
                                         widget=forms.TextInput(attrs={
                                             'placeholder': 'dlg_filename'}))  # default: dpf_filename.dlg   can be ommitted
    param_k = forms.BooleanField(required=False, label="-k",
                                 help_text="Keep original residue numbers")
    param_i = forms.BooleanField(required=False, label="-i",
                                 help_text="Ignore header-checking")
    param_t = forms.BooleanField(required=False, label="-t",
                                 help_text="Parse the PDBQT file to check torsions, then stop.")
    param_d = forms.BooleanField(required=False, label="-d",
                                 help_text="Increment debug level")

    def clean_param_dlg_filename(self):
        output_prefix = self.cleaned_data['param_dlg_filename']
        return get_valid_filename(output_prefix)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(Autodock4Form, self).__init__(*args, **kwargs)

        toolset = ToolSet.objects.get(p2ctool_name="autodock")

        self.fields['mpi_cluster'] = MPIModelChoiceField(queryset=get_mpi_queryset_all(self.user), label="MPI Cluster",
                                                         toolset=toolset,
                                                         help_text="Getting an empty list? Try <a href='{0}'>creating an MPI Cluster</a> first.".format(
                                                             reverse('create_mpi')))

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('mpi_cluster', wrapper_class='col-xs-12'),
            Fieldset(
                'Input parameters',
                    # Div('param_receptor_file', css_class='col-xs-12'),
                Field('param_ligand_file',wrapper_class='col-xs-12'),
                Field('param_dpf_file', wrapper_class='col-xs-12'),
                Field('param_grid_files', wrapper_class='col-xs-12'),
                    # Div('param_dat_file', css_class='col-xs-12'),
                css_class='col-xs-12'
            ),
            Fieldset(
                'Output parameters',
                AppendedText('param_dlg_filename', '.dlg', wrapper_class='col-xs-12 col-md-8'),
                css_class='col-xs-12'
            ),
            Fieldset(
                'Other parameters',
                Field('param_k', wrapper_class='col-xs-12'),
                Field('param_i', wrapper_class='col-xs-12'),
                Field('param_t', wrapper_class='col-xs-12'),
                Field('param_d', wrapper_class='col-xs-12'),
                css_class='col-xs-12'
            ),
        )


class Autogrid4Form(forms.Form):
    param_receptor_file = forms.FileField(label="Receptor file", help_text="File type: (.pdbqt)",
                                          validators=[pdbqt_file_extension_validator])
    param_ligand_file = forms.FileField(label="Ligand file", help_text="File type: (.pdbqt)",
                                        validators=[pdbqt_file_extension_validator], required=False)

    param_gpf_file = forms.FileField(label="Grid parameter file", help_text="File type: (.gpf)",
                                     validators=[gpf_file_extension_validator])
    param_glg_filename = forms.CharField(label="Grid log prefix", required=False, help_text="If specified, the output (.glg) file will be named as [glg_prefix].glg",
                                         widget=forms.TextInput(attrs={'placeholder': 'glg_prefix'}))
    param_d = forms.BooleanField(required=False, label="-d",
                                 help_text="Increment debug level")
    param_use_with_autodock = forms.BooleanField(required=False, label='Use with AutoDock', help_text="autogrid4 output will be used as input to autodock4")

    param_dpf_file = forms.FileField(required=False, label="Dock parameter file", help_text="File type: (.dpf)",
                                     validators=[dpf_file_extension_validator])  # .dpf file

    param_dlg_filename = forms.CharField(required=False, label="Dock log prefix", help_text="If specified, the output (.dlg) file will be named as [dlg_prefix].dlg",
                                         widget=forms.TextInput(attrs={
                                             'placeholder': 'dlg_prefix'}))  # default: dpf_filename.dlg   can be ommitted
    param_k = forms.BooleanField(required=False, label="-k",
                                 help_text="Keep original residue numbers")
    param_i = forms.BooleanField(required=False, label="-i",
                                 help_text="Ignore header-checking")
    param_t = forms.BooleanField(required=False, label="-t",
                                 help_text="Parse the PDBQT file to check torsions, then stop.")
    param_d_dock = forms.BooleanField(required=False, label="-d",
                                      help_text="Increment debug level")

    def clean_param_dlg_filename(self):
        output_prefix = self.cleaned_data['param_dlg_filename']
        return get_valid_filename(output_prefix)

    def clean_param_glg_filename(self):
        output_prefix = self.cleaned_data['param_glg_filename']
        return get_valid_filename(output_prefix)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(Autogrid4Form, self).__init__(*args, **kwargs)

        toolset = ToolSet.objects.get(p2ctool_name="autodock")

        self.fields['mpi_cluster'] = MPIModelChoiceField(queryset=get_mpi_queryset_all(self.user), label="MPI Cluster",
                                                         toolset=toolset,
                                                         help_text="Getting an empty list? Try <a href='{0}'>creating an MPI Cluster</a> first.".format(
                                                             reverse('create_mpi')))

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'autogrid4',
                    # Div(
                    Field('mpi_cluster', wrapper_class='col-xs-12 col-md-8'),
                    Field('param_use_with_autodock', wrapper_class='col-xs-12 col-md-3 col-md-offset-1'),
                    Fieldset(
                        'Input parameters',

                        Field('param_receptor_file', wrapper_class='col-xs-12'),
                        Field('param_gpf_file', wrapper_class='col-xs-12'),
                        css_class='col-xs-12'

                    ),
                    Fieldset(
                        'Output parameters',
                        AppendedText('param_glg_filename', '.glg', wrapper_class='col-xs-12 col-md-8'),
                        css_class='col-xs-12'
                    ),
                    Fieldset(
                        'Other parameters',
                        Field('param_d', wrapper_class='col-xs-12'),
                        css_class='col-xs-12'
                    ),
                ),
                Tab(
                    'autodock4',
                    Fieldset(
                        'Input parameters',
                        Field('param_ligand_file', wrapper_class='col-xs-12'),
                        Field('param_dpf_file', wrapper_class='col-xs-12'),
                        css_class='col-xs-12'
                    ),
                    Fieldset(
                        'Output parameters',
                        AppendedText('param_dlg_filename', '.dlg', wrapper_class='col-xs-12 col-md-8'),
                        css_class='col-xs-12'
                    ),
                    Fieldset(
                        'Other parameters',
                        Field('param_k', wrapper_class='col-xs-12'),
                        Field('param_i', wrapper_class='col-xs-12'),
                        Field('param_t', wrapper_class='col-xs-12'),
                        Field('param_d_dock', wrapper_class='col-xs-12'),
                        css_class='col-xs-12'
                    ),
                )
            )
        )

    def clean(self):
        if self.cleaned_data['param_use_with_autodock']:
            if not self.cleaned_data['param_dpf_file']:
                raise forms.ValidationError(u'Missing dock parameter file', code="missing_dock_parameter")
            if not self.cleaned_data['param_ligand_file']:
                raise forms.ValidationError(u'Missing ligand parameter file', code="missing_ligand_parameter")
