"""
Created on Jan 28, 2013

@author: agross
"""

import os as os
import pickle as pickle
from collections import defaultdict

import pandas as pd
import numpy as np
from Helpers.Misc import make_path_dump

from Processing.ProcessClinical import get_clinical
from Data.Annotations import read_in_pathways


def tree():
    return defaultdict(tree)


class Run(object):
    """
    Object for storing meta-data and functions for dealing with Firehose runs.
    Entry level for loading data from pre-processed dumps in the ucsd_analyses
    file tree.
    """
    
    def __init__(self, date, version, data_path, result_path, parameters,
                 cancer_codes, sample_matrix, description=''):
        self.date = date
        self.data_path = data_path
        self.version = version
        self.result_path = result_path
        self.report_path = result_path
        self.parameters = parameters
        self.dependency_tree = tree()
        self.description = description
        self.cancer_codes = cancer_codes
        self.sample_matrix = sample_matrix
        self.cancers = np.array(self.sample_matrix.index[:-1])
        self.data_types = np.array(self.sample_matrix.columns)
        if 'pathway_file' in self.parameters:
            self._init_gene_sets(parameters['pathway_file'])
        else:
            self.gene_sets = {}
            self.gene_lookup = {}
            self.genes = np.array([])
        
    def _init_gene_sets(self, gene_set_file):
        self.gene_sets, self.gene_lookup = read_in_pathways(gene_set_file)
        self.genes = np.array(self.gene_lookup.keys())
              
    def __repr__(self):
        s = 'Run object for TCGA Analysis\n'
        s += 'Firehose run date: ' + self.date + '\n'
        s += 'Code version: ' + self.version + '\n'
        if self.description:
            s += 'Comment: ' + self.description + '\n'
        return s
                 
    def load_cancer(self, cancer):
        path = '/'.join([self.report_path, cancer, 'CancerObject.p'])
        obj = pickle.load(open(path, 'rb'))
        return obj
    
    def save(self):
        self.report_path = (self.result_path + 'Run_' + 
                            self.version.replace('.', '_'))
        make_path_dump(self, self.report_path + '/RunObject.p')

        
def get_run(firehose_dir, version='Latest'):
    """
    Helper to get a run from the file-system. 
    """
    path = '{}/ucsd_analyses'.format(firehose_dir)
    if version is 'Latest':
        version = sorted(os.listdir(path))[-1]
    run = pickle.load(open('{}/{}/RunObject.p'.format(path, version), 'rb'))
    return run
        

class Cancer(object):
    def __init__(self, name, run):
        self.name = name
        if name in run.cancer_codes:
            self.full_name = run.cancer_codes.ix[name]
        else:
            self.full_name = name
        counts = run.sample_matrix.ix[name]
        self.samples = counts[counts > 0]
        self.data_types = np.array(self.samples.index)
        self.run_path = run.report_path
        self.path = '/'.join([self.run_path, self.name])
    
    def load_clinical(self):
        path = '/'.join([self.path, 'Clinical', 'ClinicalObject.p'])
        obj = pickle.load(open(path, 'rb'))
        return obj
    
    def load_global_vars(self):
        path = '/'.join([self.path, 'Global_Vars.csv'])
        df = pd.read_csv(path, index_col=0)
        ft = pd.MultiIndex.from_tuples
        df.columns = ft(map(lambda s: eval(s, {}, {}), df.columns))
        return df
    
    def load_data(self, data_type):
        path = '/'.join([self.path, data_type, 'DataObject.p'])
        obj = pickle.load(open(path, 'rb'))
        return obj
        
    def __repr__(self):
        return self.full_name + '(\'' + self.name + '\') cancer object'
    
    def initialize_data(self, run, save=False, get_vars=False):
        clinical = Clinical(self, run)
        clinical.artificially_censor(5)
        # global_vars = IM.get_global_vars(run.data_path, self.name)
        # global_vars = global_vars.groupby(level=0).first()
        
        if save is True:
            self.save()
            clinical.save()
            # global_vars.to_csv(self.path + '/Global_Vars.csv') 
        
        if get_vars is True:
            return clinical
            # return clinical, global_vars        
    
    def save(self):
        self.path = '{}/{}'.format(self.run_path, self.name)
        make_path_dump(self, self.path + '/CancerObject.p')        
    
    
class Clinical(object):
    def __init__(self, cancer, run, patients=None):
        """

        :param cancer: Cancer object
        :param run: Run object
        :param patients: list of patients to filter down to (optional)
        """
        self.cancer = cancer.name
        self.run_path = run.report_path
        self.path = '/'.join([self.run_path, cancer.name])
        
        tup = get_clinical(cancer.name, run.data_path, patients)
        (self.clinical, self.drugs, self.followup, self.stage,
         self.timeline, self.survival) = tup

    def __repr__(self):
        return 'Clinical Object for ' + self.cancer
        
    def artificially_censor(self, years):
        for n, s in self.survival.iteritems():
            if n.endswith('y'):
                continue
            df = s.unstack().copy()
            df['event'] = df.event * (df.days < int(365.25 * years))
            df['days'] = df.days.clip_upper(int((365.25 * years)))
            self.survival[n + '_' + str(years) + 'y'] = df.stack()
            
    def save(self):
        self.path = '{}/{}'.format(self.run_path, self.cancer)
        make_path_dump(self, self.path + '/Clinical/ClinicalObject.p')
        if self.drugs is not None:
            self.drugs.to_csv(self.path + '/Clinical/drugs.csv')
        if self.survival is not None:
            self.survival.to_csv(self.path + '/Clinical/survival.csv')
        self.timeline.to_csv(self.path + '/Clinical/timeline.csv')
        self.clinical.to_csv(self.path + '/Clinical/clinical.csv')


def patient_filter(df, can):
    if can.patients is not None:
        return df[[p for p in df.columns if p in can.patients]]
    elif can.filtered_patients is not None:
        return df[[p for p in df.columns if p not in can.filtered_patients]]
    else:
        return df           


class Dataset(object):
    def __init__(self, cancer_path, data_type, compressed=True):
        self.data_type = data_type  
        self.path = '{}/{}'.format(cancer_path, data_type)
        self.compressed = compressed

        self.patients = []
        self.df = None
        self.features = None
        return
        
    def compress(self):
        assert len(self.df.shape) == 2
        self.patients = self.df.columns
        self.df = self.df.replace(0, np.nan).stack()
        if self.features is not None:
            self.features = self.features.replace(0, np.nan).stack()
        self.compressed = True
        
    def uncompress(self):
        assert len(self.df.shape) == 1
        self.df = self.df.unstack().ix[:, self.patients].fillna(0.)
        if self.features is not None:
            self.features = self.features.unstack().ix[:, self.patients]
            self.features = self.features.fillna(0.)
        self.compressed = False
        
    def save(self):
        if self.compressed is False:
            self.compress()
        make_path_dump(self, self.path + '/DataObject.p')
            
    def __repr__(self):
        return self.data_type + ' dataset'
