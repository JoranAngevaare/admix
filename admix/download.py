import os
import sys
from argparse import ArgumentParser
from admix.interfaces.rucio_summoner import RucioSummoner
from admix.interfaces.database import ConnectMongoDB
from admix.utils.naming import make_did
import time
import utilix

DB = ConnectMongoDB()

def determine_rse(rse_list, glidein_country):
    # TODO put this in config or something?
    EURO_SITES = ["CCIN2P3_USERDISK",
                  "NIKHEF_USERDISK",
                  "NIKHEF2_USERDISK",
                  "WEIZMANN_USERDISK",
                  "CNAF_USERDISK",
                  "SURFSARA_USERDISK"]

    US_SITES = ["UC_OSG_USERDISK", "UC_DALI_USERDISK"]


    if glidein_country == "US":
        in_US = False
        for site in US_SITES:
            if site in rse_list:
                return site

        if not in_US:
            print("This run is not in the US so can't be processed here. Exit 255")
            sys.exit(255)

    elif glidein_country == "FR":
        for site in EURO_SITES:
            if site in rse_list:
                return site

    elif glidein_country == "NL":
        for site in reversed(EURO_SITES):
            if site in rse_list:
                return site

    elif glidein_country == "IL":
        for site in EURO_SITES:
            if site in rse_list:
                return site

    elif glidein_country == "IT":
        for site in EURO_SITES:
            if site in rse_list:
                return site

    if US_SITES[0] in rse_list:
        return US_SITES[0]
    else:
        raise AttributeError("cannot download data")


def download(number, dtype, hash, chunks=None, location='.',  tries=3,  version='latest',
             metadata=True, **kwargs):
    """Function download()
    
    Downloads a given run number using rucio
    :param number: A run number (integer)
    :param dtype: The datatype to download.
    :param chunks: List of integers representing the desired chunks. If None, the whole run will be downloaded.
    :param location: String for the path where you want to put the data. Defaults to current directory.
    :param tries: Integer specifying number of times to try downloading the data. Defaults to 2.
    :param version: Context version as listed in the data_hashes collection
    :param kwargs: Keyword args passed to DownloadDids
    """

    # setup rucio client
    rc = RucioSummoner()

    # get DID
    did = make_did(number, dtype, hash)

    # if we didn't pass an rse, determine the best one
    rse = kwargs.pop('rse', None)
    if not rse:
        # determine which rses this did is on
        rules = rc.ListDidRules(did)
        rses = []
        for r in rules:
            if r['state'] == 'OK':
                rses.append(r['rse_expression'])
        # find closest one
        rse = determine_rse(rses, os.environ.get('GLIDEIN_Country', 'US'))

    if chunks:
        dids = []
        for c in chunks:
            cdid = did + '-' + str(c).zfill(6)
            dids.append(cdid)
        # also download metadata
        if metadata:
            dids.append(did + '-metadata.json')

    else:
        dids = [did]

    # rename the folder that will be downloaded
    path = did.replace(':', '-')
    # drop the xnt at the beginning
    path = path.replace('xnt_', '')

    location = os.path.join(location, path)
    os.makedirs(location, exist_ok=True)

    print(f"Downloading {did}")

    _try = 1
    success = False

    while _try <= tries and not success:
        if _try > 0:
            rse = None
        result = rc.DownloadDids(dids, download_path=location, no_subdir=True, rse=rse, **kwargs)
        if isinstance(result, int):
            print(f"Download try #{_try} failed.")
            _try += 1
            time.sleep(5)
        else:
            success = True

    if success:
        print(f"Download successful to {location}")


def main():
    parser = ArgumentParser("admix-download")

    parser.add_argument("number", type=int, help="Run number to download")
    parser.add_argument("dtype", help="Data type to download")
    parser.add_argument("--chunks", nargs="*", help="Space-separated list of chunks to download.")
    parser.add_argument("--location", help="Path to put the downloaded data.", default='.')
    parser.add_argument('--tries', type=int, help="Number of tries to download the data.", default=2)
    parser.add_argument('--rse', help='RSE to download from')
    parser.add_argument('--context', help='strax context you need -- this determines the hash',
                         default='xenonnt_online')

    args = parser.parse_args()

    hash = utilix.db.get_hash(args.context, args.dtype)

    if args.chunks:
        chunks = [int(c) for c in args.chunks]
    else:
        chunks=None

    download(args.number, args.dtype, hash, chunks=chunks, location=args.location, tries=args.tries,
             rse=args.rse)

