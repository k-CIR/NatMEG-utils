

from datetime import datetime
import sys
from tkinter.filedialog import askopenfilename, asksaveasfile
import re
from os.path import basename, join, isdir, exists
import os
from glob import glob
import pandas as pd
from os.path import exists, dirname
import os
import yaml
import tkinter as tk
import json

default_output_path = '/neuro/data/local'
noise_patterns = ['empty', 'noise', 'Empty']
proc_patterns = ['tsss', 'sss', r'corr\d+', r'ds\d+', 'mc', 'avgHead']
headpos_patterns = ['trans', 'headpos']
opm_exceptions_patterns = ['HPIbefore', 'HPIafter', 'HPImiddle',
                           'HPIpre', 'HPIpost']

def log(
    message: str,
    level: str='info',
    logfile: str='log.log',
    logpath: str='.'):
    """
    Print a message to the console and write it to a log file.
    Parameters
    ----------
    message : str
        The message to print and write to the log file.
    level : str
        The log level. Can be 'info', 'warning', or 'error'.
    logfile : str
        The name of the log file.
    logpath : str
        The path to the log file.
    """ 

    # Define colors for different log levels
    level_colors = {
        'info': '\033[94m',   # Blue
        'warning': '\033[93m',   # Yellow
        'error': '\033[91m'    # Red
    }
    
    # Check if the log level is valid
    if level not in level_colors:
        print(f"Invalid log level '{level}'. Supported levels are: info, warning, error.")
        return

    # Get the current timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Format the message
    formatted_message = f"""
    {level_colors[level]}[{level.upper()}] {timestamp}
    {message}\033[0m
     """

    if not exists(logpath):
        os.makedirs(logpath, exist_ok=True)
    # Create the log file if it doesn't exist
    if not exists(f'{logpath}/{logfile}'):
        with open(f'{logpath}/{logfile}', 'w') as f:
            f.write('Level\tTimestamp\tMessage\n')
            f.write('-----\t---------\t-------\n')
    
    # Write the message to the log file
    with open(f'{logpath}/{logfile}', 'a') as f:
        f.write(f"[{level.upper()}]\t{timestamp}\t{message}\n")
    print(formatted_message)

def file_contains(file: str, pattern: list):
    return bool(re.compile('|'.join(pattern)).search(file))

def askForConfig():
    """_summary_

    Args:
        file_config (str, optional): _description_. Defaults
            to None.

    Returns:
        dict: dictionary with the configuration parameters
    """
    option = input("Do you want to open an existing config file or create a new? ([open]/new/cancel): ").strip().lower()
    # Check if the file is defined or ask for it
    if option not in ['o', 'open']:
        if option in ['n', 'new']:
            return 'new'
        elif option in ['c', 'cancel']:
            print('User cancelled')
            sys.exit(1)

    else:
        file_name = askopenfilename(
            title='Select config file',
            filetypes=[('YAML files', '*.yml'), ('JSON files', '*.json')],
            initialdir=default_output_path)

        if not file_name:
            print('No configuration file selected. Exiting opening dialog')
            sys.exit(1)
        
        print(f'{file_name} selected')
        return file_name

def extract_info_from_filename(file_name: str):
    
    """_summary_
    
    Function to clean up filenames and extract
    
    Args:
        file_name (str, required): _description_
        
    Returns:
        dict: 
            filename (str): _description_
            participant (str): _description_
            task (str): _description_
            processing (list): _description_
            datatypes (list): _description_
            extension (str): _description_
    """
    
    # Extract participant, task, processing, datatypes and extension
    participant = re.search(r'(NatMEG_|sub-)(\d+)', file_name).group(2)
    extension = '.' + re.search(r'\.(.*)', file_name).group(1)
    datatypes = list(set([r.lower() for r in re.findall(r'(meg|raw|opm|eeg|behav)', basename(file_name), re.IGNORECASE)] +
                         ['opm' if 'kaptah' in file_name else '']))
    datatypes = [d for d in datatypes if d != '']

    proc = re.findall('|'.join(proc_patterns), basename(file_name))
    desc = re.findall('|'.join(headpos_patterns), basename(file_name))

    split = re.search(r'(\-\d+\.fif)', basename(file_name))
    split = split.group(1).strip('.fif') if split else ''
    
    exclude_from_task = '|'.join(['NatMEG_'] + ['sub-'] + ['proc']+ datatypes + [participant] + [extension] + proc + [split] + ['\\+'] + ['\\-'] + desc)
    
    if file_contains(file_name, opm_exceptions_patterns):
        datatypes.append('opm')
    
    if 'opm' in datatypes or 'kaptah' in file_name:    
        task = re.split('_', basename(file_name), flags=re.IGNORECASE)[-2].replace('file-', '')
        task = re.split('opm', task, flags=re.IGNORECASE)[0]

    else:
        task = re.sub(exclude_from_task, '', basename(file_name), flags=re.IGNORECASE)
    task = [t for t in task.split('_') if t]
    if len(task) > 1:
        task = ''.join([t.title() for t in task])
    else:
        task = task[0]

    if file_contains(task, noise_patterns):
        try:
            task = f'Noise{re.search("before|after", task.lower()).group().title()}'
        except:
            task = 'Noise'

    info_dict = {
        'filename': file_name,
        'participant': participant,
        'task': task,
        'split': split,
        'processing': proc,
        'description': desc,
        'datatypes': datatypes,
        'extension': extension
    }
    
    return info_dict

def default_config():
    default_dict = {
        'project': {
            'name': '',
            'InstitutionName': 'Karolinska Institutet',
            'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
            'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
            'description': 'project for MEG data',
            'tasks': [''],
            'squidMEG': 'neuro/data/local/',
            'opmMEG': 'neuro/data/local/',
            'BIDS': 'neuro/data/local/',
            'Calibration': 'neuro/databases/sss/sss_cal.dat',
            'Crosstalk': 'neuro/databases/ctc/ct_sparse.fif'
            },
        'bids': {
            'Dataset_description': 'dataset_description.json',
            'Participants': 'participants.tsv',
            'Participants_mapping_file': 'participant_mapping_example.csv',
            'Original_subjID_name': 'old_subject_id',
            'New_subjID_name': 'new_subject_id',
            'Original_session_name': 'old_session_id',
            'New_session_name': 'new_session_id',
            'Overwrite': False
        },
        'maxfilter': {
            'standard_settings': {'trans_conditions': ['AudOdd',
                'Phalanges',
                'RSEO',
                'RSEC'],
            'trans_option': 'continous',
            'merge_runs': True,
            'empty_room_files': ['empty_room_before.fif', 'empty_room_after.fif'],
            'sss_files': '',
            'autobad': True,
            'badlimit': '7',
            'bad_channels': '',
            'tsss_default': True,
            'correlation': '0.98',
            'movecomp_default': True,
            'subjects_to_skip': ''
            },
        'advanced_settings': {
            'force': False,
            'downsample': False,
            'downsample_factor': '4',
            'apply_linefreq': False,
            'linefreq_Hz': '50',
            'maxfilter_version': '/neuro/bin/util/maxfilter',
            'MaxFilter_commands': ''
            }
        }
    }
    return default_dict
    # yaml.safe_dump(default_dict, open('default_config.yml', 'w'), default_flow_style=False, sort_keys=False)

def openConfigUI(file_name: str = None):
    """_summary_
    Creates or opens a JSON file with MaxFilter parameters using a GUI.

    Parameters
    ----------
    default_data : dict, optional
        Default data to populate the GUI fields.

    Returns
    -------
    None
    
    """

    # Check if the configuration file exists and if so load
    if not(file_name):
        data = default_config()
    else:
        if file_name.endswith('.yml'):
            with open(file_name, 'r') as f:
                data = yaml.safe_load(f)
        elif file_name.endswith('.json'):
            with open(file_name, 'r') as f:
                data = json.load(f)
    
    # Create default configuration file

    # Create a new Tkinter window
    root = tk.Tk()
    root.title('BIDSify Configuration')
    root.geometry('500x500')
    
    # Main frame
    frame = tk.LabelFrame(root, text='BIDSify Configuration')
    frame.grid(row=0, column=0,
                ipadx=5, ipady=5, sticky='e')
    
    # Buttons frame
    button_frame = tk.LabelFrame(root, text="", padx=10, pady=10, border=0)
    button_frame.grid(row=1, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
    
    # Create labels and entries for each field in the configuration
    chb = {}
    keys = []
    entries = []
    for i, key in enumerate(data):
        val = data[key]
        
        label = tk.Label(frame, text=key).grid(row=i, column=0, sticky='e')

        if val in ['on', 'off']:
            chb[key] = tk.StringVar()
            chb[key].set(val)
            check_box = tk.Checkbutton(frame,
                                       variable=chb[key], onvalue='on', offvalue='off',
                                       text='')
            
            check_box.grid(row=i, column=1, padx=2, pady=2, sticky='w')
            entry = chb[key]
        else:
            entry = tk.Entry(frame, width=30)
            entry.grid(row=i, column=1)
            entry.insert(0, val)
        
        keys.append(key)
        entries.append(entry)
    
    # Create buttons to save or cancel the configuration
    def cancel():
            root.destroy()
            print('Closed')
            sys.exit(1)

    def save():
        data = {}

        for key, entry in zip(keys, entries):
            if ', ' in entry.get():
                data[key] = [x.strip() for x in entry.get().split(', ') if x.strip()]
            else:
                data[key] = entry.get()
            
        # Replace with save data
        save_path = asksaveasfile(defaultextension=".json", filetypes=[("JSON files", "*.json")],
                                  initialdir='/neuro/data/local')
        if save_path:
            with open(save_path.name, 'w') as f:
                json.dump(data, f, indent=4, default=list)
            print(f"Settings saved to {save_path.name}")

        root.destroy()
        print(f'Saving BIDS parameters to {json_name}')

    save_button = tk.Button(button_frame,
                            text="Save", command=save)
    save_button.grid(row=0, column=0)

    cancel_button = tk.Button(button_frame,
                            text="Cancel", command=cancel)
    cancel_button.grid(row=0, column=2)

    # Start GUI loop
    root.mainloop()
    return data

#### Not in use ####
def get_desc_from_raw(file_name):
    info = mne.io.read_info(file_name, verbose='error')
    
    update_dict = {
        
    }

def generate_new_conversion_table(
    config_dict: dict,
    overwrite=False):
    
    """
    For each participant and session within MEG folder, move the files to BIDS correspondent folder
    or create a new one if the session does not match. Change the name of the files into BIDS format.
    """
    ts = datetime.now().strftime('%Y%m%d')
    path_triux = config_dict['squidMEG']
    path_opm = config_dict['opmMEG']
    path_BIDS = config_dict['BIDS']
    participant_mapping = config_dict['Participants mapping file']
    old_subj_id = config_dict['Original subjID name']
    new_subj_id = config_dict['New subjID name']
    old_session = config_dict['Original session name']
    new_session = config_dict['New session name']
    
    processing_modalities = []
    if path_triux != '' and str(path_triux) != '()':
        processing_modalities.append('triux')
    if path_opm != '' and str(path_opm) != '()':
        processing_modalities.append('hedscan')
    
    processing_schema = {
        'time_stamp': [],
        'run_conversion': [],
        'participant_from': [],
        'participant_to': [],
        'session_from': [],
        'session_to': [],
        'task': [],
        'split': [],
        'run': [],
        'datatype': [],
        'acquisition': [],
        'processing': [],
        'raw_path': [],
        'raw_name': [],
        'bids_path': [],
        'bids_name': []
    }
    
    if participant_mapping:
        mapping_found=True
        try:
            pmap = pd.read_csv(participant_mapping, dtype=str)
        except FileExistsError as e:
            mapping_found=False
            print('Participant file not found, skipping')
    
    
    for mod in processing_modalities:
        if mod == 'triux':
            path = path_triux
            participants = [p for p in glob('NatMEG*', root_dir=path) if isdir(join(path, p))]
        elif mod == 'hedscan':
            path = path_opm
            participants = [p for p in glob('sub*', root_dir=path) if isdir(join(path, p))]

        for participant in participants:
            
            if mod == 'triux':
                sessions = [session for session in glob('*', root_dir=join(path, participant)) if isdir(join(path, participant, session))]
            elif mod == 'hedscan':
                sessions = list(set([f.split('_')[0][2:] for f in glob('*', root_dir=join(path, participant))]))

            for date_session in sessions:
                
                session = date_session
                
                if mod == 'triux':
                    all_fifs = sorted(glob('*.fif', root_dir=join(path, participant, date_session, 'meg')))
                elif mod == 'hedscan':
                    all_fifs = sorted(glob('*.fif', root_dir=join(path, participant)))

                for file in all_fifs:
                    
                    if mod == 'triux':
                        full_file_name = join(path, participant, date_session, 'meg', file)
                    elif mod == 'hedscan':
                        full_file_name = join(path, participant, file)
                    
                    if exists(full_file_name):
                        info_dict = extract_info_from_filename(full_file_name)
                    
                    task = info_dict.get('task')
                    proc = '+'.join(info_dict.get('processing'))
                    datatypes = '+'.join([d for d in info_dict.get('datatypes') if d != ''])
                    subject = info_dict.get('participant')
                    split = info_dict.get('split')
                    run = ''
                    
                    if participant_mapping and mapping_found:
                        pmap = pd.read_csv(participant_mapping, dtype=str)
                        subject = pmap.loc[pmap[old_subj_id] == subject, new_subj_id].values[0].zfill(3)
                        
                        session = pmap.loc[pmap[old_session] == date_session, new_session].values[0].zfill(2)
                    
                    info = mne.io.read_raw_fif(full_file_name,
                                    allow_maxshield=True,
                                    verbose='error')
                    ch_types = set(info.get_channel_types())

                    if 'mag' in ch_types:
                        datatype = 'meg'
                        extension = '.fif'
                    elif 'eeg' in ch_types:
                        datatype = 'eeg'

                    bids_path = BIDSPath(
                        subject=subject,
                        session=session,
                        task=task,
                        acquisition=mod,
                        processing=None if proc == '' else proc,
                        run=None if run == '' else run,
                        datatype=datatype,
                        root=path_BIDS
                    )
                    
                    # Check if bids exist
                    run_conversion = 'yes'
                    if (find_matching_paths(bids_path.directory,
                                        tasks=task,
                                        acquisitions=mod,
                                        extensions='.fif')):
                        run_conversion = 'no'

                    processing_schema['time_stamp'].append(ts)
                    processing_schema['run_conversion'].append(run_conversion)
                    processing_schema['participant_from'].append(participant)
                    processing_schema['participant_to'].append(subject)
                    processing_schema['session_from'].append(date_session)
                    processing_schema['session_to'].append(session)
                    processing_schema['task'].append(task)
                    processing_schema['split'].append(split)
                    processing_schema['run'].append(run)
                    processing_schema['datatype'].append(datatype)
                    processing_schema['acquisition'].append(mod)
                    processing_schema['processing'].append(proc)
                    processing_schema['raw_path'].append(dirname(full_file_name))
                    processing_schema['raw_name'].append(file)
                    processing_schema['bids_path'].append(bids_path.directory)
                    
                    processing_schema['bids_name'].append(bids_path.basename)
                    

    df = pd.DataFrame(processing_schema)
    
    df.insert(2, 'task_count',
              df.groupby(['participant_to', 'acquisition', 'datatype', 'split', 'task', 'processing'])['task'].transform('count'))
    
    df.insert(3, 'task_flag', df.apply(
                lambda x: 'check' if x['task_count'] != df['task_count'].max() else 'ok', axis=1))
    

    os.makedirs(f'{path_BIDS}/conversion_logs', exist_ok=True)
    df.to_csv(f'{path_BIDS}/conversion_logs/{ts}_bids_conversion.tsv', sep='\t', index=False)

def load_conversion_table(config_dict: dict,
                          conversion_file: str=None):
        # Load the most recent conversion table
    path_BIDS = config_dict.get('BIDS')
    conversion_logs_path = join(path_BIDS, 'conversion_logs')
    if not os.path.exists(conversion_logs_path):
        print("No conversion logs directory found.")
        return None
        
    if not conversion_file:
        print(f"Loading most recent conversion table from {conversion_logs_path}")
        conversion_files = sorted(glob(join(conversion_logs_path, '*_bids_conversion.tsv')))
        if not conversion_files:
            print("Creating new conversion table")
            generate_new_conversion_table(config_dict)
            
        conversion_files = sorted(glob(join(conversion_logs_path, '*_bids_conversion.tsv')))

        latest_conversion_file = conversion_files[-1]
        print(f"Loading the most recent conversion table: {basename(latest_conversion_file)}")
        conversion_table = pd.read_csv(latest_conversion_file, sep='\t', dtype=str)
    else: 
        conversion_table = pd.read_csv(conversion_file, sep='\t', dtype=str)
        
    return conversion_table