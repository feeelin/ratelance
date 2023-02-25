from bcutils import decode_text, encode_text, load_transactions, shorten_escape
from signing import retrieve_auth_wallet, sign_send
from colors import h, nh, b, nb
from keyring import Keyring 

from base64 import b64decode, b16encode
import traceback

from tonsdk.boc import Builder, Cell
from tonsdk.utils import Address
from tslice import Slice



JOB_NOTIFICATIONS = 'EQA__RATELANCE_______________________________JvN'


def job_data_init(poster: str, value: int, desc: Cell, key: int) -> Cell:
  di = Builder()
  di.store_uint(0, 2)
  di.store_address(Address(poster))
  di.store_uint(value, 64)
  di.store_ref(desc)
  di.store_uint(key, 256)
  return di.end_cell()


def job_state_init(poster: str, value: int, desc: Cell, key: int) -> Cell:
  with open(__file__ + '/../assets/contract-job.boc', 'rb') as f:
    code = Cell.one_from_boc(f.read())
  
  si = Builder()
  si.store_uint(6, 5)
  si.store_ref(code)
  si.store_ref(job_data_init(poster, value, desc, key))
  return si.end_cell()


def analytic_msg(job: Address, value: int, desc: Cell, key: int) -> Cell:
  am = Builder()
  am.store_address(job)
  am.store_uint(value, 64)
  am.store_ref(desc)
  am.store_uint(key, 256)
  return am.end_cell()


def load_jobs(start_lt=None, custom_notif_addr=None):
  if start_lt: raise Exception('loading specific jobs not supported')
  
  notif = custom_notif_addr or JOB_NOTIFICATIONS
  for tx in load_transactions(notif, start_lt=start_lt):
    try:
      body = Cell.one_from_boc(b64decode(tx['in_msg']['msg_data'])).begin_parse()
      job = body.load_msg_addr()
      poster = Address(tx['in_msg']['source']['address']).to_string(True, True, True)
      value = body.load_uint(64)
      desc = body.load_ref()
      desc_text = decode_text(desc)
      poster_key = body.load_uint(256)
      
      # TODO: skip notifications with value < 0.05 TON
      
      if job.hash_part != job_state_init(poster, value, desc, poster_key).bytes_hash():
        print(f'{b}Found notification with invalid job address:{nb}', job.to_string())
        print(f'* {h}poster:      {nh}{poster}')
        print(f'* {h}description: {nh}{repr(desc_text)}')
      else:
        yield (job.to_string(True, True, True), poster, value, desc_text)
    except Exception as exc:
      print(f'{b}Failure while processing notification:{nb}', repr(exc))


def show_jobs(start_lt=None, custom_notif_addr=None, validate_jobs=False):
  if validate_jobs: raise Exception('validating jobs not supported')
  
  for (job, poster, value, desc) in load_jobs(start_lt, custom_notif_addr):
    jid = job[40:]
    print(f'Order [{h}{jid}{nh}] {job}')
    print(f'- {h}posted by{nh} {poster}')
    print(f'- {h}promising{nh} {value/1e9} TON, {h}staked{nh} <unknown>')
    print('-', shorten_escape(desc))


def post_job(value: int, stake: int, desc_text: str, keyring: Keyring, key_id: str):
  print(f'\n{h}Creating new job{nh}', repr(desc_text))
  
  key_info = keyring.keys_info[key_id]
  assert key_info['key_id'] == key_id
  public_key = int.from_bytes(key_info['public'], 'big')
  
  WAY_PROMPT = f'Send via mnemonic [{h}m{nh}]/wallet seed [{h}s{nh}]/ton link [{h}t{nh}]? '
  while (auth_way := input(WAY_PROMPT).lower()) not in ('m', 's', 't'): pass
  
  wallet = None
  poster = None
  
  if auth_way == 't':
    while True:
      try:
        poster = Address(input(f'{b}Your address: {nb}'))
        break
      except KeyboardInterrupt:
        raise
      except Exception:
        pass
  else:
    wallet = retrieve_auth_wallet(auth_way)
    poster = wallet.address.to_string(True, True, True)
  
  desc = encode_text(desc_text)
  si = job_state_init(poster, value, desc, public_key)
  addr = Address('0:' + b16encode(si.bytes_hash()).decode('ascii'))
  am = analytic_msg(addr, value, desc, public_key)
  
  jobs = Address(JOB_NOTIFICATIONS)
  jobs.is_bounceable = False
  
  print()
  sign_send([
    (addr, si,   Cell(), stake),
    (jobs, None, am,     5*10**7),
  ], 'creating job', auth_way, wallet)


def process_jobs_cmd(command, keyring):
  if command == 'jl':
    show_jobs()
  elif command == 'jp':
    possible_keys = list(keyring.keys_info.keys())
    if len(possible_keys) > 3:
      possible_keys_s = '/'.join(possible_keys[:3]) + '/...'
    else:
      possible_keys_s = '/'.join(possible_keys) or '<nothing available>'
    
    key_id = input(f'Used key ({possible_keys_s}): ')
    value = int(1e9 * float(input('Promised job value (TON): ')))
    stake = int(1e9 * float(input('Send stake (TON): ')))
    desc_text = input('Job description: ')
    
    post_job(value, stake, desc_text, keyring, key_id)
  else:
    print(f'{b}not implemented:{nb} {repr(command)}')