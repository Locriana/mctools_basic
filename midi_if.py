from time import sleep
import time
import subprocess
import re
import mido

MIDI_NOTE_MIN               = 0x00
MIDI_NOTE_MAX               = 0x7F
MIDI_NOTE_NB                = 0x80

MIDI_STATUS_NOTE_OFF        = 0x80
MIDI_STATUS_NOTE_ON         = 0x90
MIDI_STATUS_POLY_AFTERTOUCH = 0xA0
MIDI_STATUS_CONTROL_CHANGE  = 0xB0
MIDI_STATUS_PROGRAM_CHANGE  = 0xC0
MIDI_STATUS_CH_AFTERTOUCH   = 0xD0
MIDI_STATUS_PITCH_WHEEL     = 0xE0

MIDI_STATUS_SYSEX_START   = 0xF0
MIDI_STATUS_SYSEX_END     = 0xF7

MIDI_STATUS_QFRAME_MTC    = 0xF1
MIDI_STATUS_SONG_PTR      = 0xF2
MIDI_STATUS_SONG_SELECT   = 0xF3
MIDI_STATUS_TUNE_REQUEST  = 0xF6

MIDI_STATUS_TIMING_CLOCK    = 0xF8
MIDI_STATUS_START           = 0xFA
MIDI_STATUS_CONTINUE        = 0xFB
MIDI_STATUS_STOP            = 0xFC
MIDI_STATUS_ACTIVE_SENSING  = 0xFE
MIDI_STATUS_SYSTEM_RESET    = 0xFF

MIDI_SYSEX_MTC        = 0x7F

MIDI_CC_VOLUME        = 0x07
MIDI_CC_MODWHEEL      = 0x01
MIDI_CC_BANK_MSB      = 0x00
MIDI_CC_BANK_LSB      = 0x20

MIDI_ROLAND_MANUF_ID    = 0x41
MIDI_ROLAND_CC_FILTER_KNOB  = 0x80
MIDI_ROLAND_CC_MOD_KNOB     = 0x81
MIDI_ROLAND_CC_FX_KNOB      = 0x82
MIDI_ROLAND_CC_SOUND_KNOB    = 0x83



class MidiIf:
  def __init__(self,ch_map=None,iface='alsa'):
    self.iface = iface
    self.model_name = ''
    # self.port = None
    self.input_port_name = ''
    self.output_port_name = ''
    self.model_names = ["MC-707", "MC-101", "MV-1"]
    self.model_id = 0
    self.detect_port()
    self.last_ch = 1
    
    #mapping of MIDI channels to track indices
    if ch_map is None:
      self.ch_map = [1,2,3,4,5,6,7,8]
    else:
      self.ch_map = ch_map
    
    print(f"detected model={self.model_name}, input: {self.input_port_name}, output: {self.output_port_name}")
    
  def note(self,ch,note,velocity=100,duration=1.0):
    self.note_on(ch,note,velocity)
    sleep(duration)
    self.note_off(ch,note,velocity)
  
  def tx_status(self,ch_idx,status,data1,data2,debug=False):
    if debug == True:
      print(f"tx_status: ch_idx={ch_idx:02X} status={status:02X} data1={data1:02X} data2={data2:02X}")
    status = (status & 0xF0) | (ch_idx & 0x0F)
    data1 = data1 & 0x7F
    data2 = data2 & 0x7F
    txbuf = [status, data1, data2]
    self.transfer(txbuf,debug=True)
  
  def note_on(self,ch_idx,note,velocity=100):
    self.tx_status(ch_idx,MIDI_STATUS_NOTE_ON,note,velocity)
    
  def note_off(self,ch_idx,note,velocity=100):
    self.tx_status(ch_idx,MIDI_STATUS_NOTE_OFF,note,velocity)
  
  
  def __transfer_alsa(self, request, timeout=0.5, debug=False):
    print('transfer_alsa...')
    # Convert request list of ints -> hex string like "F0 7E 7F 06 01 F7"
    hex_request = " ".join(f"{b:02X}" for b in request)
    cmd = ["amidi", "-p", self.port, "-t", str(timeout), "-d", "-S", hex_request]

    if debug:
        print("Running command:", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
    except FileNotFoundError:
        raise RuntimeError("amidi not found. Install alsa-utils.")

    if debug:
        print("stdout:", repr(result.stdout))
        print("stderr:", repr(result.stderr))
        print("return code:", result.returncode)

    # Remove "N bytes read" lines, keep only hex
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if not re.match(r"^\d+ bytes read$", line.strip())
    ]

    if not lines:
        return None

    # Join lines and keep only hex chars
    hex_only = "".join(re.findall(r"[0-9A-Fa-f]+", "".join(lines)))
    if not hex_only:
        return None

    # Parse continuous hex string into bytes
    tokens = [hex_only[i:i+2] for i in range(0, len(hex_only), 2)]
    try:
        response = [int(tok, 16) for tok in tokens]
    except ValueError:
        raise RuntimeError(f"Unexpected amidi output: {lines}")
    if debug:
      print(f"MIDI response: {self.__intlist_to_hex_str(response)}")
    return response
  
  # I had a problem communicating with MC-707 using mido in Linux
  # It hanged randomly just after a transfer when performing
  # a large number of transfers - I tried debugging it in vscode, but no luck.
  # It might be something internal
  # idk for sure, but maybe this? https://github.com/orgs/mido/discussions/367
  def __transfer_mido(self, request, timeout=0.5, debug=False):
    time.sleep(0.02)
    if debug==True: print(f'transfer, rq: {self.intlist_to_hex_str(request)}')
    try:
      # txmsg = mido.Message.from_hex(hex_request)
      txmsg = mido.Message('sysex',data=request[1:-1])
    except Exception as e:
      print(f'mido.Message.from_hex exception: {str(e)}')
    if debug==True: print(f'mido tx message: {txmsg.hex()}')
  
    res = None    
    
    with mido.open_output(self.input_port_name) as outport, mido.open_input(self.output_port_name) as inport:
      #time.sleep(0.1)
      outport.send(txmsg)
      if txmsg.type != 'sysex':
        if debug==True: print('txed, ignoring a response (if any)')
        return []
      
      # time.sleep(0.1)
      if debug==True: print(f'txed, waiting for sysex resp, timeout = {timeout} s')
      msg = None
      start = time.time()
      while time.time() - start < timeout:
        for msg in inport.iter_pending():
          if debug==True: print('*',end='')
          if msg.type == 'sysex':
            res = list(msg.data)
            if debug==True: print(f'rxed sysex resp: {self.intlist_to_hex_str(res)}')
            break
        if res is not None:
          break
        time.sleep(0.01)
      # return empty list in case no response is rxed
      if res is None:
        res = []
      else:
        #re-create the sysex start and end for compatibility
        res.insert(0,0xF0)
        res.append(0xF7)
        print(f'near exit, now the message: {self.__intlist_to_hex_str(res)}')
        return res
    return res
  
  #Send a MIDI message with amidi or mido and return the response
  def transfer(self, request, timeout=0.5, debug=False):
    if debug==True:
      print(f"MIDI transfer: {self.intlist_to_hex_str(request)}")
    if self.iface == 'alsa':
      return self.__transfer_alsa(request,timeout=timeout,debug=debug)
    elif self.iface == 'mido':
      return self.__transfer_mido(request,timeout=timeout,debug=debug)
    else:
      print(f'mctools/midi_if/transfer: unrecognized iface parameter: {self.iface}')
      return None
    # hex_request = " ".join(f"{b:02X}" for b in request)
  
  def __find_port_idx(self,port_list,name):
    for idx,port in enumerate(port_list):
      if name in port:
        print(f'name {name} found @ idx={idx}')
        return idx
    return None


    
  def __detect_port_alsa(self):
    cmd = ["amidi", "--list-devices"]
    print("Running cmd:"," ".join(cmd))
    try:
      result = subprocess.run(
        cmd,
        capture_output = True,
        text = True,
        check = False
      )
    except FileNotFoundError:
      raise RuntimeError("amidi not found. Install alsa or whatever. It just doesn't work :/")
    print("stdout:", repr(result.stdout))
    print("stderr:", repr(result.stderr))
    print("return code:", result.returncode)
    
    res = result.stdout.split();
    print("res split: ",res)
    
    model_names = {"MC-707", "MC-101", "MV-1"}
    # model_ids = [0x5D, 0x5E, 0x6F]
    
    for idx, item in enumerate(res):
      if item in model_names:
        self.port = res[idx - 1] if idx > 0 else None
        self.model_name = item
  

  def __detect_port_mido(self):
    print("MidiIf: trying to detect_instrument_and_port...")
    input_port_list = mido.get_input_names()
    output_port_list = mido.get_output_names()
    print(f"inputs: {input_port_list}")
    print(f"outputs: {output_port_list}")
    input_idx = None
    output_idx = None
    
    #input
    for name in self.model_names:
      print(f'name: {name}')
      input_idx = self.__find_port_idx(input_port_list,name)
      if input_idx is not None:
        self.model_name = name
        break
    #output:
    for name in self.model_names:
      print(f'name: {name}')
      output_idx = self.__find_port_idx(output_port_list,name)
      if output_idx is not None:
        self.model_name = name
        break
      
    print(f'idxes: in={input_idx}, out={output_idx}')
    if input_idx is not None:
      self.input_port_name = input_port_list[input_idx]
      
    if output_idx is not None:
      self.output_port_name = output_port_list[output_idx]
        
  def get_model_id(self,debug=False):
    # identity request
    req = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
    if debug: print(f'running get_model_id, transfer...')
    res = midi.transfer(req,debug=debug)
    if debug: print(f'res ponse to id req: {self.__intlist_to_hex_str(res)}')
    # example from MC-707: 7E 7F 06 02 41 5D 03 00 00 00 01 00 00
    try:
      self.model_id = res[6]
      return self.model_id
    except Exception as e:
      print(f'get_model_id, exception: {str(e)}')
    return 0
    
  def detect_port(self):
    if self.iface == 'alsa':
      return self.__detect_port_alsa()
    elif self.iface == 'mido':
      return self.__detect_port_mido()
    else:
      print(f'mctools/midi_if/detect_port: unrecognized iface parameter: {self.iface}')
      return None
  
  #this part definitely needs cleaning up...
  def __intlist_to_hex_str(self,intlist):
    return f"{' '.join(f'{n:02X}' for n in intlist)}"
    
  def intlist_to_hex_str(self,intlist):
    return f"{' '.join(f'{n:02X}' for n in intlist)}"
  
    
if __name__ == "__main__":
  # midi = MidiIf(iface='mido')
  midi = MidiIf(iface='alsa')
  print(f'in/out port names: {midi.input_port_name} / {midi.output_port_name}')
  req = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
  res = midi.transfer(req,timeout=1.0)
  print(f'midi transfer res: {midi.intlist_to_hex_str(res)}')
  sleep(1)
  print(f'reading model id...')
  print(f'model id: {midi.get_model_id(debug=False):02X}')
  
