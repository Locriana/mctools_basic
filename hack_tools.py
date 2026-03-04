import datetime
import csv
from midi_if import MidiIf
from sys_ex_comm import SysExComm
import subprocess
import shutil

class HackTools:
  def __init__(self,comm):
    self.comm = comm
  
  def intlist_to_hex_str(self,intlist):
    return f"{' '.join(f'{n:02X}' for n in intlist)}"

  def _limit_to_printable_ascii(self,i):
    if i >= 0x20 and i < 0x7F:
      return i
    else:
      return ord('.')

  def intlist_to_str(self,intlist):
    return f"{''.join(f'{chr(self._limit_to_printable_ascii(n))}' for n in intlist)}"
  
  # An example of a reg dump procedure
  # it's super dirty but it worked for me to figure out the address map
  # it creates and updates (appends data to) a simple CSV file if the the script could read the data
  def dump(self,start_address,input_chunk=None,length=None,end_address=0x80000000,out_file_name='dump_fine.csv',scan_step=0,fill=None,debug=True):
    if length is not None:
      if debug: print(f"length arg is set to {length} -> computing end address")
      end_address = start_address + int(length)
    start_address = int(start_address)
    print(f'starting register fine dump procedure. Start=0x{start_address:08X}, end=0x{end_address:08X}')
    chunk_size = 16
    if input_chunk is not None:
      result = input_chunk
    else:
      result = []
    
    if scan_step < chunk_size:
      scan_step = chunk_size
    
    for address in range(start_address,end_address,scan_step):
      if address & 0x80808080 != 0: continue
      if debug: print(f'---> poking up to {chunk_size} bytes from address 0x{address:08X}')
      result_chunk_raw = comm.roland_request(address,chunk_size,debug=False)
      result_len = len(result_chunk_raw)
      
      if fill is not None:
        if result_len < chunk_size:
          print(f"+++++++ fill result_len {result_len} < chunk_size {chunk_size}, filling with {fill}")
          missing_nb = chunk_size - result_len
          fill_list = [fill] * missing_nb
          print(f"chunk raw before {result_chunk_raw}, fill={fill_list}")
          result_chunk_raw.extend(fill_list)
          print(f"chunk raw after {result_chunk_raw}")
          result_len = len(result_chunk_raw)
      
      #result_len is zero if a location is empty
      if result_len > 0:
        address_hex = f'{address:08X}'
        print(f'got response from {address_hex}, len {result_len}')
        
        for i in range(0,result_len):
          item = { "address": i+address, "data": result_chunk_raw[i]}
          result.append(item)
        
        if out_file_name is not None:
          value_list = str(self.intlist_to_hex_str(result_chunk_raw))
          ascii_interp = str(self.intlist_to_str(result_chunk_raw))
          line = [[address_hex,result_len,value_list,ascii_interp]]
          print(f'line to write: {line}')
          with open( out_file_name, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(line)
    return result
  
  # Compare two lists of {"address": int, "data": int} dicts.
  # Return a list of dicts describing differences.
  def list_diff(self, list_a, list_b):
      # Build address -> data lookup tables
      map_a = {entry["address"]: entry["data"] for entry in list_a}
      map_b = {entry["address"]: entry["data"] for entry in list_b}

      diffs = []

      # Only compare addresses present in both
      for addr in map_a.keys() & map_b.keys():
          before = map_a[addr]
          after = map_b[addr]
          if before != after:
              diffs.append({
                  "address": addr,
                  "before": before,
                  "after": after
              })

      # Optional: sort by address for nicer output
      diffs.sort(key=lambda x: x["address"])

      return diffs

  # Display differences in a readable terminal format.
  def disp_diff(self, diff_list):
      for entry in diff_list:
          addr = entry["address"]
          before = entry["before"]
          after = entry["after"]

          print(
              f"Address 0x{addr:08X}: change from 0x{before:02X} to 0x{after:02X}"
          )

  def dump_settings(self,filename,basic=True):
    rxdata = self.dump(0x00000000,end_address=0x00000030,input_chunk=None,out_file_name=filename,debug=False,fill=0x00)
    if basic==True:
      rxdata = self.dump(0x10000000,end_address=0x10001000,input_chunk=rxdata,out_file_name=filename,debug=False,fill=0x00)
    else:
      rxdata = self.dump(0x10000000,end_address=0x10004000,input_chunk=rxdata,out_file_name=filename,debug=False,fill=0x00)
    return rxdata
  
  
  
  # this one uses uses kompare tools that works in GUI
  # less nerdy, but more readable than in the terminal
  def diff_with_kompare(self,file1: str, file2: str) -> None:
      if not shutil.which("kompare"):
          raise RuntimeError("kompare not found in PATH")
      subprocess.Popen(["kompare", file1, file2])

  def diff(self,file1: str, file2: str) -> None:
      subprocess.Popen(["diff", "-ys", file1, file2])




if __name__ == "__main__":
  print(f"running hack_tools as the main module")
  midi = MidiIf(iface='mido')
  # midi = MidiIf(iface='alsa')
  comm = SysExComm(midi)
  hack = HackTools(comm)

  timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
  timestamp = timestamp.replace(":","-")
  subdir_name = "dumps"

  # settings dump
  # set to False to deactivate
  if True:
    basic_only = True
    filename_before = f"{subdir_name}/dump_{timestamp}_settings_before.csv"
    rxdata_before = hack.dump_settings(filename_before,basic=basic_only)
    input("now change something and press enter")
    filename_after = f"{subdir_name}/dump_{timestamp}_settings_after.csv"
    rxdata_after = hack.dump_settings(filename_after,basic=basic_only)
    diff_list = hack.list_diff(rxdata_before,rxdata_after)
    print("the list of differences:")
    hack.disp_diff(diff_list)
    hack.diff_with_kompare(filename_before,filename_after)
    exit()
