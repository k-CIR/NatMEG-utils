#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Created on Thu Jan 25 14:16:49 2024

@author: andger
"""
#%%
from glob import glob
import os
from os.path import exists, basename, dirname, isdir
import sys
import re
import tkinter as tk
from tkinter.filedialog import askdirectory, askopenfilename, asksaveasfile
import json
import pandas as pd
import subprocess
import argparse
from datetime import datetime
from shutil import copy2
import mne
from mne.transforms import (invert_transform,
                            read_trans, write_trans)
from mne.preprocessing import compute_average_dev_head_t
from mne.chpi import (compute_chpi_amplitudes, compute_chpi_locs,
                      head_pos_to_trans_rot_t, compute_head_pos,
                      write_head_pos,
                      read_head_pos)
import matplotlib.patches as mpatches
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import (
    log,
    proc_patterns,
    noise_patterns,
    file_contains,
    askForConfig
)

###############################################################################
# Global variables
###############################################################################
default_raw_path = '/neuro/data/sinuhe'
default_output_path = '/neuro/data/local'
default_base_path = os.getcwd()


exclude_patterns = [r'-\d+.fif', '_trans', 'opm',  'eeg', 'avg.fif']
global data

debug = True
###############################################################################

# TODO:
# - Integrate with Bids?

def match_task_files(files, task: str):
    matched_files = [f for f in files if not file_contains(basename(f).lower(), exclude_patterns + proc_patterns) and task in f]
    return matched_files

def askForProjectDir():
    data_path = askdirectory(title='Select project for MEG data', initialdir=default_raw_path)  # shows dialog box and return the MEG path
    print("The folder selected for MEG data is %s." % str(data_path))

    if not data_path:
        if not debug:
            print('No data folder selected. Exiting...')
            sys.exit(1)
        else:
            data_path = None
    else:
        return data_path

def defaultMaxfilterConfig():
    data = {
    'standard_settings': {
        ## STEP 1: On which conditions should average headposition be done (consistent naming is mandatory!)?
        'project_name': '',
        'trans_conditions': ['task1', 'task2'],
        'trans_option': 'continous',
        'merge_runs': 'on',

        ## STEP 2: Put the names of your empty room files (files in this array won't have "movecomp" applied) (no commas between files and leave spaces between first and last brackets)
        'empty_room_files': ['empty_room_before', 'empty_room_after'],
        'sss_files': [],

        ## STEP 3: Select MaxFilter options (advanced options)
        'autobad': 'on',
        'badlimit': 7,
        'bad_channels':[''],
        'tsss_default': 'on',
        'correlation': 0.98,
        'movecomp_default': 'on',
        'data_path': '/neuro/data/sinuhe',
        'output_path': '',
        'subjects_to_skip': []
        },
    'advanced_settings': {
        'force': 'off',
        'downsample': 'off',
        'downsample_factor': 4,
        'apply_linefreq': 'off',
        'linefreq_Hz': 50,
        'cal': '/neuro/databases/sss/sss_cal.dat',
        'ctc': '/neuro/databases/ctc/ct_sparse.fif',
        'maxfilter_version': '/neuro/bin/util/maxfilter',
        'MaxFilter_commands': ''
        }
    }
    return data

def OpenMaxFilterSettingsUI(json_name: str = None):
    """
    Creates or opens a JSON file with MaxFilter parameters using a GUI.

    Parameters
    ----------
    data : dict, optional
        Default data to populate the GUI fields.

    Returns
    -------
    data : dict
    """
    if not json_name:
        data = defaultMaxfilterConfig()
    else:
        with open(json_name, 'r') as f:
            data = json.load(f)

    if not data['standard_settings']['data_path']:
        data['standard_settings']['data_path'] = askForProjectDir()

    standard_settings = data['standard_settings']
    advanced_settings = data['advanced_settings']

    # Create main window
    root = tk.Tk()
    root.eval('tk::PlaceWindow . center')
    root.title("MaxFilter Settings")

    # Create standard settings section
    std_frame = tk.LabelFrame(root, text="Standard Settings", padx=20, pady=20, border=2)
    std_frame.grid(row=0, column=0, ipadx=5, ipady=5, sticky='ns')
    
    std_chb = {}
    std_entries = {}
    for i, (key, value) in enumerate(standard_settings.items()):
        
        label = tk.Label(std_frame, text=key)
        label.grid(row=i, column=0, sticky="e", padx=2, pady=2)
        
        if key == 'trans_option':
            print(i, key, value)
            selected_option = tk.StringVar()

            options = [value] + list(
                {'continous', 'initial'} - {value})
            entry = tk.OptionMenu(std_frame, selected_option, *options)
            entry.grid(row=i, column=1, padx=2, pady=2, sticky='w')
            selected_option.set(options[0])
            std_entries[key] = selected_option
        
        elif value in ['on', 'off']:
            std_chb[key] = tk.StringVar()
            std_chb[key].set(value)
            check_box = tk.Checkbutton(std_frame,
                                    variable=std_chb[key], onvalue='on', offvalue='off',
                                    text='')

            check_box.grid(row=i, column=1, padx=2, pady=2, sticky='w')
            std_entries[key] = std_chb[key]
        
        else:
            if isinstance(value, list):
                value = ', '.join(value)
            entry = tk.Entry(std_frame, width=40)
            entry.insert(0, value)
            entry.grid(row=i, column=1, padx=2, pady=2)
            std_entries[key] = entry

    # Create advanced settings section
    adv_frame = tk.LabelFrame(root, text="Advanced Settings", padx=20, pady=20, border=2)

    adv_chb = {}
    adv_entries = {}
    for i, (key, value) in enumerate(advanced_settings.items()):
        label = tk.Label(adv_frame, text=key)
        label.grid(row=i, column=0, sticky="e", padx=2, pady=2)
        
        if key == 'maxfilter_version':
            selected_option = tk.StringVar()
            # options = ['/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter']
            # WARNING. mfiler is a new experimental version, seems to find extremly many bad channels
            options = options = [value] + list(
                {'/neuro/bin/util/maxfilter', '/neuro/bin/util/mfilter'} - {value})
            entry = tk.OptionMenu(adv_frame, selected_option, *options)
            entry.grid(row=i, column=1, padx=2, pady=2, sticky='w')
            selected_option.set(options[0])
            adv_entries[key] = selected_option
        
        elif value in ['on', 'off']:
            adv_chb[key] = tk.StringVar()
            adv_chb[key].set(value)
            check_box = tk.Checkbutton(adv_frame,
                                    variable=adv_chb[key], onvalue='on', offvalue='off',
                                    text='')
            check_box.grid(row=i, column=1, padx=2, pady=2, sticky='w')
            adv_entries[key] = adv_chb[key]
            
        else:
            if isinstance(value, list):
                value = ', '.join(value)

            entry = tk.Entry(adv_frame, width=40)
            entry.insert(0, value)
            entry.grid(row=i, column=1, padx=2, pady=2)
            adv_entries[key] = entry

    # Buttons frame
    button_frame = tk.Frame(root, padx=10, pady=10)
    button_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

    def toggle_advanced():
        if adv_frame.winfo_ismapped():
            adv_frame.grid_forget()
            toggle_button.config(text="Show Advanced Settings")
        else:
            adv_frame.grid(row=0, column=1, ipadx=5, ipady=5, sticky='ns')
            toggle_button.config(text="Hide Advanced Settings")

    def save():
        for key, entry in std_entries.items():
            value = entry.get()
            std_entries[key] = value.split(', ') if ', ' in value else value
        for key, entry in adv_entries.items():
            value = entry.get()
            adv_entries[key] = value.split(', ') if ', ' in value else value
        
        data['standard_settings'] = std_entries
        data['advanced_settings'] = adv_entries

        save_path = asksaveasfile(defaultextension=".json", filetypes=[("JSON files", "*.json")],
                                  initialdir=default_output_path)
        if save_path:
            with open(save_path.name, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Settings saved to {save_path.name}")
        root.destroy()

    def cancel():
        root.destroy()
        print("Operation canceled.")
        sys.exit(1)

    save_button = tk.Button(button_frame, text="Save & Run", command=save)
    save_button.grid(row=0, column=0, padx=5, pady=5)

    toggle_button = tk.Button(button_frame, text="Show Advanced Settings", command=toggle_advanced)
    toggle_button.grid(row=0, column=1, padx=5, pady=5)

    cancel_button = tk.Button(button_frame, text="Cancel", command=cancel)
    cancel_button.grid(row=0, column=2, padx=5, pady=5)

    # Start GUI loop
    root.mainloop()
    return data

def plot_movement(raw, head_pos, mean_trans):

    if isinstance(head_pos, str):
        head_pos = read_head_pos(head_pos)
    if isinstance(mean_trans, str):
        mean_trans = read_trans(mean_trans)
        
    original_head_dev_t = invert_transform(raw.info["dev_head_t"])
    
    """
    Plot trances of movement for insepction. Uses mne.viz.plot_head_positions
    """
    fig = mne.viz.plot_head_positions(head_pos, mode='traces', show=False)
    red_patch = mpatches.Patch(color='r', label='Original')
    green_patch = mpatches.Patch(color='g', label='Average')

    for ax, ori, av in zip(fig.axes[::2],
                            original_head_dev_t['trans'][:3, 3],
                            mean_trans['trans'][:3, 3]):
        ax.axhline(1000*ori, color="r")
        ax.axhline(1000*av, color="g")
        
    fig.legend(handles=[red_patch, green_patch], loc='upper left')
    fig.tight_layout()
    return fig

def import_conversion_table(conversion_file: str):
        
    df = pd.read_csv(conversion_file, sep='\t')
    df = df.where(pd.notnull(df), None)
    df['run_maxfilter'] = 'no'
    df = df[df['acquisition'] == 'triux']
    df = df[df['datatype'] == 'meg']
    df = df[df['split'].isna()]
    
    for _, d in df.groupby(['participant_to', 'session_to', 'task']):
        if len(d) == 1:
            df.loc[d.index[0], 'run_maxfilter'] = 'yes'

    # df = df[df['run_maxfilter'] == 'yes']
    
    return df.reset_index(drop=True)

def MaxFilter_from_conversion_table(conversion_file: str):
        
    df = import_conversion_table(conversion_file)
    df = df.where(pd.notnull(df), None)
    
    for _, d in df.iterrows():
        print(d)
        

class set_parameter:
    def __init__(self, mxf, mne_mxf, string):
        self.mxf = mxf
        self.mne_mxf = mne_mxf
        self.string = string

class MaxFilter:
    
    def __init__(self, config_dict: dict, **kwargs):
        
        parameters = config_dict['standard_settings'] | config_dict['advanced_settings']

        self.parameters = parameters
    
    def create_task_headpos(self, 
                            data_path: str,
                            out_path: str,
                            task: str,
                            files: list | str,
                            overwrite=False,
                            **kwargs):

        parameters = self.parameters

        merge_headpos = parameters.get('merge_runs')

        headpos_name = f"{out_path}/{task}_headpos.pos"
        trans_file = f"{out_path}/{task}_trans.fif"
        fig_name = f"{out_path}/{task}_movement.png"

        if not exists(headpos_name) or overwrite:
            
            if isinstance(files, str):
                files = [files]
            raws = [mne.io.read_raw_fif(
                    f'{data_path}/{file}',
                    allow_maxshield=True,
                    verbose='error')
                        for file in files]
            
            if merge_headpos == 'on' and len(files) > 1:
                raws[0].info['dev_head_t'] = raws[1].info['dev_head_t']
                raw = mne.concatenate_raws(raws)
            else:
                raw = raws[0]
            print(f"Creating average head position for files: {' | '.join(files)}")
            chpi_amplitudes = compute_chpi_amplitudes(raw)
            chpi_locs = compute_chpi_locs(raw.info, chpi_amplitudes)
            head_pos = compute_head_pos(raw.info, chpi_locs, verbose='error')
            
            write_head_pos(headpos_name, head_pos)
            print(f"Wrote headposition file to: {basename(headpos_name)}")
        else:
            print(f'{basename(headpos_name)} already exists. Skipping...')
        
        if not exists(trans_file) or overwrite:

            if isinstance(files, str):
                files = [files]
            raws = [mne.io.read_raw_fif(
                    f'{data_path}/{file}',
                    allow_maxshield=True,
                    verbose='error')
                        for file in files]
            
            if merge_headpos == 'on' and len(files) > 1:
                raws[0].info['dev_head_t'] = raws[1].info['dev_head_t']
                raw = mne.concatenate_raws(raws)
            else:
                raw = raws[0]

            head_pos = read_head_pos(headpos_name)
            # trans, rot, t = head_pos_to_trans_rot_t(head_pos) 

            mean_trans = invert_transform(
                compute_average_dev_head_t(raw, head_pos))
            
            write_trans(trans_file, mean_trans, overwrite=True)
            print(f'Wrote trans file to {basename(trans_file)}')
        
        else:
            print(f'{basename(trans_file)} already exists. Skipping...')
        
        if not exists(fig_name) or overwrite:
            plot_movement(raw, headpos_name, trans_file).savefig(fig_name)

    def set_params(self, subject, session, task):
        
        parameters = self.parameters
        """_summary_

        Args:
            subject (str): _description_
            task (str): _description_
        """
            
        data_root = os.path.join(parameters.get('data_path'),
                                 parameters.get('project_name'))
        output_path = parameters.get('output_path')
        # Check if output path is set
        if not output_path:
            output_path = data_root

        subj_path = f'{output_path}/{subject}/{session}/meg'
        trans_file = f'{subj_path}/{task}_trans.fif'
        trans_conditions = parameters.get('trans_conditions')
        trans_option = parameters.get('trans_option')

        def set_trans(param=None):
            if 'continous' in trans_option and task in trans_conditions:
                if param:
                    mxf = '-trans %s' % param
                    mne_mxf = '--trans=%s' % param
                    string = 'avgHead'
            else:
                mxf=''
                mne_mxf = ''
                string = ''
                print('No information about trans')
                #sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _trans = set_trans(trans_file)
        
        # create set_force function
        def set_force(param=None):
            if param == 'on':
                mxf = '-force'
            elif param == 'off':
                mxf = ''
            else:
                print('faulty "force" setting (must be on or off)')
                sys.exit(1)
            return(mxf)
        _force = set_force(parameters.get('force'))
        
        def set_cal(param=None):
            if param:
                mxf = '-cal %s' % param
                mne_mxf = '--calibration=%s' % param
                string = 'cal_'
            else:
                print('no "cal" file found')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _cal = set_cal(parameters.get('cal'))
        
        def set_ctc(param=None):
            if param:
                mxf = '-ctc %s' % param
                mne_mxf = '--cross_talk=%s' % param
                string = 'ctc_'
            else:
                print('no "ctc" file found')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _ctc = set_ctc(parameters.get('ctc'))
        
        # create set_mc function (sets movecomp according to wishes above and abort if set incorrectly, this is a function such that it can be changed throughout the script if empty_room files are found) 
        def set_mc(param=None):
            if param == 'on':
                mxf = '-movecomp'
                mne_mxf = '--movecomp'
                string='mc'
            elif param == 'off':
                mxf = ''
                mne_mxf = ''
                string = ''
            else:
                print('faulty "movecomp" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _mc = set_mc(parameters.get('movecomp_default'))
        # If empty room file set tsss off and remove trans and headpos
        if file_contains(task, noise_patterns):
            _mc.mxf = ''
            _mc.mne_mxf = ''
            _mc.string = ''

        # create set_tsss function
        def set_tsss(param=None):
            if param == 'on':
                mxf = '-st'
                mne_mxf='--st'
                string='tsss'
            elif param == 'off':
                mxf = ''
                mne_mxf=''
                string=''
            else:
                print('faulty "tsss" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf,mne_mxf, string))
        _tsss = set_tsss(parameters.get('tsss_default'))
        
        # create set_ds function
        def set_ds(param=None):
            if param == 'on':
                if int(parameters.get('downsample_factor')) > 1:
                    mxf = '-ds %s' % parameters.get('downsample_factor')
                    mne_mxf = ''
                    string = 'dsfactor-%s_' % \
                        parameters.get('downsample_factor')
                else:
                    print('downsampling factor must be an INTEGER greater than 1')
            elif param == 'off':
                mxf = ''
                mne_mxf = ''
                string=''
            else:
                print('faulty "downsampling" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _ds = set_ds(parameters.get('downsample'))

        def set_corr(param=None):
            if param:
                mxf = '-corr %s' % param
                mne_mxf = '--corr=%s' % param
                string = 'corr %s_' % \
                    round(float(param)*100)
            elif not param:
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "correlation" setting (must be between 0 and 1)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _corr = set_corr(parameters.get('correlation'))

        # set linefreq according to wishes above and abort if set incorrectly
        def set_linefreq(param=None):
            if param == 'on':
                mxf = '-linefreq %s' % parameters.get('linefreq_Hz')
                mne_mxf = '--linefreq %s' % parameters.get('linefreq_Hz')
                string = 'linefreq-%s_' % parameters.get('linefreq_Hz')
            elif param == 'off':
                mxf = ''
                mne_mxf = ''
                string = ''
            else:
                print('faulty "apply_linefreq" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _linefreq = set_linefreq(parameters.get('apply_linefreq'))

        # Set autobad parameters
        def set_autobad(param=None):
            if param == 'on':
                mxf = '-autobad %s -badlimit %s' % (param, parameters.get('badlimit'))
                mne_mxf = '--autobad=%s' % parameters.get('badlimit')
                string = 'autobad_%s' % param
            elif param == 'off':
                mxf = '-autobad %s' % param
                mxf = '--autobad %s' % param
                string = ''
            else:
                print('faulty "autobad" setting (must be on or off)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _autobad = set_autobad(parameters.get('autobad'))

        def set_bad_channels(param=None):
            if param:
                if isinstance(param, list):
                    bad_ch = ' '.join(param)
                else:
                    bad_ch = param
                mxf = '-bad %s' % bad_ch
                mne_mxf = '--bad %s' % bad_ch
                string = '_bad_%s' % bad_ch
            elif not param:
                mxf = ''
                mne_mxf= ''
                string=''
            else:
                print('faulty "bad_channels" setting (must be comma separated list)')
                sys.exit(1)
            return(set_parameter(mxf, mne_mxf, string))
        _bad_channels = set_bad_channels(parameters.get('bad_channels'))

        tsss_default = parameters.get('tsss_default')
        
        if task in parameters.get('sss_files'):
            tsss_default = 'off'

        def set_bids_proc():
            proc = []
            if tsss_default == 'on':
                proc.append(_tsss.string)
                if parameters.get('correlation'):
                    proc.append(f'corr{round(float(parameters.get('correlation'))*100)}')
            else:
                proc.append('sss')

            if parameters.get('movecomp_default') == 'on':
                proc.append(_mc.string)
            
            if 'continous' in trans_option and task in parameters.get('trans_conditions'):
                proc.append(_trans.string)
            
            proc = [p for p in proc if p != '']

            return('+'.join(proc))
        _proc = set_bids_proc()
        
        _merge_runs = parameters.get('merge_runs')
        _additional_cmd = parameters.get('MaxFilter_commands')

        self._trans = _trans
        self._force = _force
        self._cal = _cal
        self._ctc = _ctc
        self._ds = _ds
        self._tsss = _tsss
        self._corr = _corr
        self._mc = _mc
        self._autobad = _autobad
        self._bad_channels = _bad_channels
        self._linefreq = _linefreq
        self._proc = _proc
        self._merge_runs = _merge_runs
        self._additional_cmd = _additional_cmd

    def run_command(self, subject, session):

        parameters = self.parameters

        data_root = os.path.join(parameters.get('data_path'),
                                 parameters.get('project_name'))
        output_path = parameters.get('output_path')
        # Check if output path is set
        if not output_path:
            output_path = data_root
 
        subj_in = f'{data_root}/{subject}/{session}/meg'
        subj_out = f'{output_path}/{subject}/{session}/meg'
        
        # Create log directory if it doesn't exist
        os.makedirs(f'{subj_out}/{'log'}', exist_ok=True)
        
        maxfilter_path = parameters.get('maxfilter_version')

        # List all files in directory
        all_fifs = sorted(glob('*.fif', root_dir=subj_in))

        # Create patterns to exclude files
        
        naming_convs = [
            'raw',
            'meg'
        ]
        naming_conv = re.compile(r'|'.join(naming_convs))
        
        trans_files = parameters.get('trans_conditions')
        sss_files = parameters.get('sss_files')
        empty_room_files = parameters.get('empty_room_files')

        if isinstance(trans_files, str):
            trans_files = [trans_files]
        if isinstance(sss_files, str):
            sss_files = [sss_files]
        if isinstance(empty_room_files, str):
            empty_room_files = [empty_room_files]

        tasks_to_run = sorted(list(set(
            trans_files +
            sss_files +
            empty_room_files)))
        
        # Remove if empty
        tasks_to_run = [t for t in tasks_to_run if t != '']

        for task in tasks_to_run:

            files = match_task_files(all_fifs, task)
            
            if not files:
                print(f'No files found for task: {task}')
                continue
            
            print(f'''
                Processing task: {task}
                Using files: 
                    {'\n'.join(files)}
                ''')

            # Average head position
            # TODO: make transname absolute path, or try relative path?
            if task in trans_files:
                self.create_task_headpos(subj_in, subj_out, task, files, overwrite=False)

            self.set_params(subject, session, task)
            
            _proc = self._proc
            
            for file in files:

                clean = file.replace('.fif', f'_proc-{_proc}.fif')
                ncov = naming_conv.search(clean)
                
                if not ncov:
                    clean = clean.replace('.fif', '_meg.fif')

                # Test absolute path
                file = f"{subj_in}/{file}"
                clean = f"{subj_out}/{clean}"
                log = f'{subj_out}/{'log'}/{basename(clean).replace(".fif",".log")}'

                command_list = []
                command_list.extend([
                    maxfilter_path,
                    '-f %s' % file,
                    '-o %s' % clean,
                    self._cal.mxf,
                    self._ctc.mxf,
                    self._trans.mxf,
                    self._tsss.mxf,
                    self._ds.mxf,
                    self._corr.mxf,
                    self._mc.mxf,
                    self._autobad.mxf,
                    self._bad_channels.mxf,
                    self._linefreq.mxf,
                    self._force,
                    self._additional_cmd,
                    '-v',
                    '| tee -a %s' % log
                    ])
                self.command_mxf = ' '.join(command_list)
                self.command_mxf = re.sub(r'\\s+', ' ', self.command_mxf).strip()

                if not exists(clean):
                    print('''
                          Running Maxfilter on
                          Subject: %s
                          Session: %s
                          Task: %s
                          ''' % (subject, 
                                 session,
                                 task))
                    if not debug:
                        subprocess.run(self.command_mxf, shell=True, cwd=subj_in)
                        log(f'{file} -> {clean}')
                    else:
                        print(self.command_mxf)

                else:
                    print('''
                        Existing file: %s
                        Delete to rerun MaxFilter process
                        ''' % clean)

        # os.chdir(default_base_path)

    def loop_dirs(self, max_workers=4):
        """Iterates over the subject and session directories and runs maxfilter in parallel."""
        parameters = self.parameters
        data_root = os.path.join(parameters.get('data_path'),
                                 parameters.get('project_name'))
        
        subjects = sorted(glob('NatMEG*', root_dir=data_root))
        skip_subjects = parameters.get('subjects_to_skip')
        print(f'Skipping {", ".join(skip_subjects)}')
        subjects = [s for s in subjects if s not in skip_subjects]

        # Collect all (subject, session) pairs
        tasks = []
        for subject in [s for s in subjects if isdir(f'{data_root}/{s}')]:
            sessions = [s for s in sorted(glob('*', root_dir=f'{data_root}/{subject}')) if isdir(f'{data_root}/{subject}/{s}')]
            for session in sessions:
                tasks.append((subject, session))

        # Run in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.run_command, subject, session) for subject, session in tasks]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in parallel task: {e}")

def args_parser():
    parser = argparse.ArgumentParser(description=
                                     '''Maxfilter
                                     
                                     Will use a configuation file to run MaxFilter on the data.
                                     Select to open an existing configuration file or create a new one.
                                     
                                     ''',
                                     add_help=True,
                                     usage='maxfilter [-h] [-c CONFIG] [-e]')
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file')
    parser.add_argument('-e', '--edit', action='store_true', help='Launch the UI for Maxfilter configuration')
    args = parser.parse_args()
    return args

# %%
def main():
    
    args = args_parser()

    if args.config:
        file_config = args.config
    else:
        file_config = askForConfig()
    
    if file_config == 'new':
        config_dict = OpenMaxFilterSettingsUI()
    elif file_config != 'new' and args.edit:
        config_dict = OpenMaxFilterSettingsUI(file_config)
    else:
        with open(file_config, 'r') as f:
            config_dict = json.load(f)

    mf = MaxFilter(config_dict)
    mf.loop_dirs()


if __name__ == "__main__":
    main()
