# -*- coding: utf-8 -*-
from __future__ import with_statement
import logging
import datetime
import os
import time
import json
import numpy as np

from admix.tasks import helper
from admix.tasks import uploader
from admix.tasks import rule_updater
from admix.runDB import xenon_runDB


class Tasker(xenon_runDB.XenonRunDatabase):
    
    def __init__(self):
        print(helper.get_hostconfig()['task'])
        #self.tasker_xrd = xenon_runDB.XenonRunDatabase().__init__()
        super(Tasker, self).__init__()
    
    def ExecuteTask(self):
        #This member function makes the book
        #of the available tasks which are specified in 
        #the configuration file
        
        #Create the query:
        self.CreateQuery()
        #Ask for the db cursor
        cursordb = self.GetCursor()
        
        print("load:", len(cursordb))

        self.GetTaskList()
        
        if self.run_task == 'upload':
            print("Run an upload session")
            uploader.Uploader(db_curser=self.GetCursor(),
                              task_list=self.GetTaskList(),
                              type_list=self.GetTypeList(),
                              detk_list=self.GetDetectorList()
                              ).run()
            
        if self.run_task == 'download':
            print("Run a download session")
            
        if self.run_task == 'rule-server':
            print("Run the rule server")
            
        if self.run_task == 'rule-updater-1t':
            print("Run a specific Xenon1T rule update")
            rule_updater.RuleUpdater(db_curser=self.GetCursor(),
                                     task_list=self.GetTaskList(),
                                     type_list=self.GetTypeList(),
                                     dest_list=self.GetDestinationList(),
                                     detk_list=self.GetDetectorList()
                                     ).run()
    
    def GetTaskList(self):
        try:
            self.run_task = helper.get_hostconfig()['task']
        except:
            print("Specify a task")
            exit()
        return self.run_task
    
    def GetTypeList(self):
        try:
            self.type_list = helper.get_hostconfig()['type'].replace(" ", "").split(",")
        except LookupError as e:
            print("No types are specified")
            exit()
            #logging.debug("task_list not specified, running all tasks")
            #return []
        return self.type_list
    
    def GetDetectorList(self):
        try:
            self.detector_list = helper.get_hostconfig()['detector'].replace(" ", "").split(",")
        except LookupError as e:
            print("No detectors are specified")
            exit()
        return self.detector_list
    
    def GetDestinationList(self):
        try:
            self.destination_list = helper.get_hostconfig()['destination'].replace(" ", "").split(",")
        except LookupError as e:
            print("No detectors are specified")
            exit()
        return self.destination_list
                               