import sys
import termios
import fcntl
import os
from time import sleep
import csv
import subprocess
import re
from midi_if import MidiIf

class SysExComm:
  def __init__(self,midi):
    self.midi = midi
    self.model_id = self.detect_id()
    self.model_name = self.midi.model_name;
    print(f"SysExComm init, id={self.model_id:02X}, name={self.model_name}")
    
  def detect_id(self):
    req = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
    res = self.midi.transfer(req)
    print(f"SysExComm, detect_id, res={self.__intlist_to_hex_str(res)}")
    return res[6]
  
  # computes checksum according to the documentation
  # substitutes the checksum byte in the provided input buffer data_in
  # returns the input buffer but with the checksum added @ [len-2]
  def __compute_checksum(self,data_in):
    try:
      if(len(data_in) < 14):
        print(f"compute_checksum: too short, len={ len(data_in) }")
        return data_in
      s = 0
      checksum_idx = len(data_in)-2
      for idx in range(8,checksum_idx):
        s += data_in[idx]
      remainder = s % 128
      checksum = 128 - remainder
      if(checksum > 0x7F):
        raise Exception(f"checksum too large value: {checksum:02X}")
      data_in[checksum_idx] = checksum
    except Exception as e:
      print(f'compute_checksum exception: {str(e)}')
    return data_in
  
  def roland_request(self,address,count,timeout=0.05,debug=False):
    if debug:
      print(f"  roland_request...")
    rq = [0xF0, 0x41, 0x10, 0x00,0x00,0x00,self.model_id, 0x11,\
      (address >> 24)&0xFF,(address >> 16)&0xFF,(address >> 8)&0xFF,address&0xFF,\
      0,0,0,count&0xFF,\
      0x00, 0xF7]
    rq = self.__compute_checksum(rq)
    response_raw = self.midi.transfer(rq,timeout,debug=True)
    if debug:
      try:
        print(f"  rq: response very raw: {self.__intlist_to_hex_str(response_raw)}")
      except:
        print(f"  rq: response very raw type: {type(response_raw)}")
    if response_raw is None:
      response_raw = []
    if len(response_raw) > 0:
      response = self.__roland_response_extract(response_raw,debug=debug)
      if debug:
        print(f"  rq: response extracted: {self.__intlist_to_hex_str(response)}")
    else:
      print(f"roland_request: no ressponse rxed from addr: {address:08X}, rq count: {count:04X}, @ timeout: {timeout} sec")
      response = []
    return response
  
  # When you see a parameter to be modiefied in the menu on the screen,
  # the timeout should be larger, because the response will arrive a bit later.
  # And when you're not looking - the default timeout should be fine ;)
  # so -> the instrument reponds faster when you're not looking xD
  # the minimum value that worked for me was 0.3s,
  # so a recommended safe value could be sth like 0.5s, but just experiment (or don't look :P)
  def roland_request_param(self,address,size,timeout=0.05,debug=False):
    param = 0
    response = self.roland_request(address,size,timeout,debug=True)
    if debug==True:
      print(f"roland_request_param, response: {self.__intlist_to_hex_str(response)}")
    for i in range(0,len(response)):
      shift = 4*(len(response)-i-1)
      if debug == True:
        print(f"shift={shift}")
      param = param | (response[i] << shift)
      if debug==True:
        print(f"roland_request_param, i={i}, param={param}")
        
    print(f"roland_request_param, returning param={param}")
    return param
    
  def __roland_response_extract(self,rxbuf,debug=False):
    if rxbuf is None: return []
    if( len(rxbuf) > 0 ):
      if debug:
        print(f"__roland_response_extract response raw: {' '.join(f'{n:02X}' for n in rxbuf)}")
        print(f"   response len={len(rxbuf)}")
    else:
      print("__roland_response_extract: no response")
      return []
    if( len(rxbuf) < 14 ):
      print(f"response too short: {len(rxbuf)}")
      print(f"  contents: {self.__intlist_to_hex_str(rxbuf)}")
      return []
    outbuf = []
    try:
      for i in range(12,len(rxbuf)-2):
        outbuf.append(rxbuf[i])
      if debug:
        print(f"extracted response (len={len(outbuf):02d}): {self.__intlist_to_hex_str(outbuf)}")
    except:
      print(f"exception happens")
    return outbuf
  
  def roland_set_param(self,address,param,size,debug=False):
    if debug:
      print(f"roland_set_param: value={param}=0x{param:02X}, size={size}")
    buf = []
    if size == 1:
      buf.append(param & 0x7F)
    else:
      for i in range(0,size):
        shift = 4*(size-i-1)
        if debug == True:
          print(f"shift={shift}")
        app_value = (param >> shift) & 0x0F
        buf.append(app_value)
        if debug==True:
          print(f"roland_set_param, i={i}, appending {app_value}")
    print(f"roland_set_param, buf to write {self.__intlist_to_hex_str(buf)}")
    self.roland_set(address,buf,debug)  
  
  def roland_set(self,address,buf,debug=False):
    dt = [0xF0, 0x41, 0x10, 0x00,0x00,0x00,self.model_id, 0x12,\
      (address >> 24)&0xFF,(address >> 16)&0xFF,(address >> 8)&0xFF,address&0xFF]
    for b in buf:
      dt.append(b)
    dt.append(0x00) # a place for a checksum
    dt.append(0xF7) # EOX
    dt = self.__compute_checksum(dt)
    if debug==True:
      print(f"roland set: {self.__intlist_to_hex_str(dt)}")
    self.midi.transfer(dt,timeout=0.2,debug=False)
    
  def mod_param_rmw(self,address,size,step,timeout=0.5,vmin=None,vmax=None,debug=True):
    value = self.roland_request_param(address,size,timeout)
    if debug==True:
      print(f'mod_param_rmw, addr={address:08X}, invalue={value}, step={step:+}')
    value = value + step
    if vmin is not None:
      if value < vmin: value = vmin
      if debug:
        print(f'value = vmin alread, not changed')
      return
    if vmax is not None:
      if value > vmax: value = vmax
      if debug:
        print(f'value = vmax already, not changed')
      return
    self.roland_set_param(address,value,size,debug=True)
    return

  def __intlist_to_hex_str(self,intlist):
    return f"{' '.join(f'{n:02X}' for n in intlist)}"


if __name__ == "__main__":
  # midi = MidiIf(iface='alsa')
  midi = MidiIf(iface='mido')
  comm = SysExComm(midi)
  trk_col_addr = [0x10000819, 0x10000A19, 0x10000C19, 0x10000E19,
    0x10001019, 0x10001219, 0x10001419, 0x10001619]
  trk_idx = 1
  debug = True
  buf = comm.roland_request(trk_col_addr[trk_idx],1,debug=False)
  color_idx = buf[0]
  if debug: print(f"get_trk_color_idx res: {color_idx}")
    

