import os.path

from django import forms

# THESE ARE VALIDATORS USED FOR FORM INPUTS

def pdbqt_file_extension_validator(file):
    ext = os.path.splitext(file.name)[1]
    if ext.lower() != '.pdbqt':
        raise forms.ValidationError(u'Only .pdbqt file accepted', code="vina_invalid_file_format")


def dpf_file_extension_validator(file):
    ext = os.path.splitext(file.name)[1]
    if ext.lower() != '.dpf':
        raise forms.ValidationError(u'Only .dpf file accepted', code="autodock_invalid_file_format")

def gpf_file_extension_validator(file):
    ext = os.path.splitext(file.name)[1]
    if ext.lower() != '.gpf':
        raise forms.ValidationError(u'Only .gpf file accepted', code="autogrid_invalid_file_format")


def grid_map_file_extension_validator(file):
    ext = os.path.splitext(file.name)[1]
    valid_extensions = ['.map', '.fld', '.xyz']
    if ext.lower() not in valid_extensions:
        raise forms.ValidationError(u'Only .map, .fld, .xyz file accepted', code="autodock_invalid_file_format")


def multi_grid_map_file_validator(files):
    for file in files:
        grid_map_file_extension_validator(file)

def dat_file_extension_validator(file):
    ext = os.path.splitext(file.name)[1]
    if ext.lower() != ".dat":
        raise forms.ValidationError(u'Only .dat file accepted', code="autodock_invalid_file_format")