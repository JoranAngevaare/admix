import os
import time
from admix.interfaces.rucio_dataformat import ConfigRucioDataFormat
from admix.interfaces.rucio_summoner import RucioSummoner
from admix.interfaces.keyword import Keyword
from admix.interfaces.database import ConnectMongoDB

DB = ConnectMongoDB()

DTYPES = ['raw_records', 'raw_records_lowgain', 'raw_records_aqmon', 'raw_records_mv']
DATADIR = '/eb/ebdata'


def get_did(run_number, dtype):
    return DB.db.find_one({'number': run_number}, {'dids': 1})['dids'][dtype]


def set_status(docid, status):
    DB.db.find_one_and_update({'_id': docid},
                              {'$set': {'status': status}}
                              )

def find_new_data():
    """"""
    query = {'number': {'$gte': 7158},
             "status": {"$exists": False},
             }

    cursor = DB.db.find(query, {'number': 1})

    for r in cursor:
        set_status(r['_id'], 'needs_upload')


def find_data_to_upload():
    cursor = DB.db.find({'status': 'needs_upload'}, {'number': 1, 'data': 1})
    ids = []

    for r in cursor:
        dtypes = set([d['type'] for d in r['data']])
        # check if all of the necessary data types are in the database
        if set(DTYPES) <= dtypes:
            ids.append(r['_id'])
    return ids


def do_upload(periodic_check=300):
    rc_reader_path = "/home/datamanager/software/admix/admix/config/xenonnt_format.config"
    rc_reader = ConfigRucioDataFormat()
    rc_reader.Config(rc_reader_path)

    rc = RucioSummoner()

    # get the data to upload
    ids_to_upload = find_data_to_upload()

    cursor = DB.db.find({'_id': {"$in": ids_to_upload}
                          #'number': 7158}
                         },
                        {'number': 1, 'data': 1, 'dids': 1})

    cursor = list(cursor)

    # check transfers
    check_transfers()
    last_check = time.time()

    for run in cursor:
        number = run['number']
        print(f"\n\nUploading run {number}")
        for dtype in DTYPES:
            print(f"\t==> Uploading {dtype}")
            # get the datum for this datatype
            datum = None
            in_rucio = False
            for d in run['data']:
                if d['type'] == dtype and 'eb' in d['host']:
                    datum = d

                if d['type'] == dtype and d['host'] == 'rucio-catalogue':
                    in_rucio = True

            if datum is None:
                print(f"Data type {dtype} not found for run {number}")
                continue

            file = datum['location'].split('/')[-1]

            #Init a class to handle keyword strings:
            keyw = Keyword()
            hash = file.split('-')[-1]
            # Apparently the GetPlugin method is stateful. It will remember previous run information
            # if you don't pass reset=True... #$%#$W^$
            rucio_template = rc_reader.GetPlugin(dtype, reset=True)
            upload_path = os.path.join(DATADIR, file)
            print(file)

            keyw.SetTemplate({'hash': hash, 'plugin': dtype, 'number':'%06d' % number})

            rucio_template = keyw.CompleteTemplate(rucio_template)

            rucio_template_sorted = [key for key in sorted(rucio_template.keys())]


            rucio_rule = rc.GetRule(upload_structure=rucio_template, rse="LNGS_USERDISK")

            print(rucio_rule)
            if not in_rucio and not rucio_rule['exists']:
                result = rc.Upload(upload_structure=rucio_template,
                                   upload_path=upload_path,
                                   rse='LNGS_USERDISK',
                                   rse_lifetime=None)

                print("Dataset uploaded")
            # if upload was successful, tell runDB
            rucio_rule = rc.GetRule(upload_structure=rucio_template, rse="LNGS_USERDISK")
            did = rucio_template[rucio_template_sorted[-1]]['did']
            print(did)
            data_dict = {'host': "rucio-catalogue",
                         'type': dtype,
                         'location': 'LNGS_USERDISK',
                         'lifetime': rucio_rule['expires'],
                         'status': 'transferred',
                         'did': did,
                         'protocol': 'rucio'
                         }

            if not in_rucio and rucio_rule['state'] == 'OK':
                DB.AddDatafield(run['_id'], data_dict)

                # add a DID list?
                # check if did field exists yet or not
                if not run.get('dids'):
                    DB.db.find_one_and_update({'_id': run['_id']},
                                              {'$set': {'dids': {dtype: did}}}
                                              )
                else:
                    print("Updating DID list")
                    DB.db.find_one_and_update({'_id': run['_id']},
                                              {'$set': {'dids.%s' % dtype: did}}
                                              )

            # add rule to OSG and Nikhef
            for rse in ['UC_OSG_USERDISK', 'UC_DALI_USERDISK']:
                add_rule(number, dtype, rse)

        if time.time() - last_check > periodic_check:
            check_transfers()
            last_check = time.time()



def add_rule(run_number, dtype, rse, lifetime=None, update_db=True):
    did = get_did(run_number, dtype)
    rc = RucioSummoner()
    result = rc.AddRule(did, rse, lifetime=lifetime)
    #if result == 1:
    #   return
    print(f"Rule Added: {did} ---> {rse}")

    if update_db:
        rucio_rule = rc.GetRule(did, rse=rse)
        data_dict = {'host': "rucio-catalogue",
                     'type': dtype,
                     'location': rse,
                     'lifetime': rucio_rule['expires'],
                     'status': 'transferring',
                     'did': did,
                     'protocol': 'rucio'
                     }
        DB.db.find_one_and_update({'number': run_number},
                                  {'$set': {'status': 'transferring'}}
                                  )

        docid = DB.db.find_one({'number': run_number}, {'_id': 1})['_id']
        DB.AddDatafield(docid, data_dict)


def check_transfers():
    cursor = DB.db.find({'status': 'transferring'}, {'number': 1, 'data': 1})

    rc = RucioSummoner()

    print("Checking transfer status of %d runs" % len(list(cursor)))

    for run in cursor:
        # for each run, check the status of all REPLICATING rules
        rucio_stati = []
        for d in run['data']:
            if d['host'] == 'rucio-catalogue':
                if d['status'] != 'transferring':
                    rucio_stati.append(d['status'])
                else:
                    did = d['did']
                    status = rc.GetRule(did, d['location'])
                    if status == 'REPLICATING':
                        rucio_stati.append('transferring')
                    elif status == 'OK':
                        # update database
                        DB.db.find_one_and_update({'_id': run['_id'],'data': {'$elemMatch': d}},
                                                  {'$set': {'data.$.status': 'transferred'}}
                                                  )
                        rucio_stati.append('transferred')

                    elif status == 'STUCK':
                        DB.db.find_one_and_update({'_id': run['_id'], 'data': {'$elemMatch': d}},
                                                  {'$set': {'data.$.status': 'error'}}
                                                  )
                        rucio_stati.append('error')


        # are there any other rucio rules transferring?
        if all([s == 'transferred' for s in rucio_stati]):
            set_status(run['_id'], 'transferred')


def clear_db():
    dtypes = ['raw_records', 'raw_records_mv', 'raw_records_aqmon', 'raw_records_lowgain']
    numbers = [7159, 7160, 7161]
    for run in numbers:
        doc = DB.GetRunByNumber(run)[0]
        docid = doc['_id']

        for d in doc['data']:
            if d['host'] == 'rucio-catalogue' and d['type'] in dtypes:
                DB.RemoveDatafield(docid, d)
                time.sleep(1)

        set_status(docid, 'needs_upload')


def main():
    while True:
        find_new_data()
        print("Starting uploads")
        do_upload()
        print("Sleeping...\n")
        #time.sleep(120)
        break



if __name__ == "__main__":
    main()
    #clear_db()
