from time import sleep
from sys_ex_comm import SysExComm
from midi_if import MidiIf


class ZenCoreTools:
  def __init__(self,comm,z_core_base=0x30000000):
    self.comm = comm
    self.clips_per_track = 16
    self.z_core_base = z_core_base
    self.base_address = z_core_base
    # this many bytes is between adjacent base addresses
    # of the zen core tones
    # this is also the number to which the tone structs are aligned to
    self.tone_alignment = 0x20000
    print(f"ZenCoreTools constructor, comm obj: {self.comm}")
  
  def coarse_tune_rmw(self,sound_base_address, step, debug=False):
    print(f'Coarse tune {step:+}')
    coarse_tune_offset = 0x0018
    #read
    rx_buf = comm.roland_request(sound_base_address+coarse_tune_offset,1)
    coarse_tune = rx_buf[0]
    if coarse_tune is None:
      print('rq1_read_param returned None, exit')
      return False
    #modify
    coarse_tune += step
    #check
    if coarse_tune > 112: coarse_tune = 112
    if coarse_tune < 16: coarse_tune = 16
    #write the modified value
    tx_buf = []
    tx_buf.append(coarse_tune)
    comm.roland_set(sound_base_address+coarse_tune_offset,tx_buf)
    return True
  
  
  # if you don't specify clip, you get the base address for the track sound
  # otherwise specify a clip_idx between 0 and 15 for a given track
  # specify clip and track by their indices (track from 0 to 7 & clips from 0 to 15)
  # whenever you see the _idx suffix, it means that something starts from 0
  def get_base_address(self,track_idx,clip_idx=None,debug=False):
    number_of_clips = 16
    
    #input check and pre-processing
    if track_idx < 0: track_idx = 0
    if track_idx > 8: track_idx = 8
    
    if clip_idx is not None:
      if clip_idx < 0: clip_idx = 0
      if clip_idx > self.clips_per_track-1: clip_idx = self.clips_per_track-1
    
    #base addresses of the 8 tracks
    mc_track_base = \
      [0x30000000, 0x30220000, 0x30440000, 0x30660000,\
       0x31080000, 0x312A0000, 0x314C0000, 0x316E0000]
    
    if clip_idx is not None:
      self.base_address = mc_track_base[track_idx] + self.tone_alignment * clip_idx
      if debug==True:
        print(f'Selecting trk={track_idx+1}, clip={clip_idx+1} @ base_address=0x{self.base_address:08X}')
    else: #when clip_idx is None:
      self.base_address = mc_track_base[track_idx] + self.tone_alignment * self.clips_per_track
      if debug==True:
        print(f'Selecting trk={track_idx+1} @ base_address=0x{self.base_address:08X}')
    return self.base_address

  def disp_map(self):
    print(f"Zen-Core memory map for tone tracks")
    for trk_idx in range(0,8):
      print(f"track: {trk_idx+1} sound @ addr={self.get_base_address(trk_idx):08X}")
      for clip_idx in range(0,16):
        print(f"    clip: {clip_idx+1} @ addr={self.get_base_address(trk_idx,clip_idx):08X}")
  
if __name__ == "__main__":
  midi = MidiIf(iface='alsa')
  # midi = MidiIf(iface='mido')
  comm = SysExComm(midi)
  zcore = ZenCoreTools(comm)

  trk_idx = 1
  clip_idx = 0
  base_address = zcore.get_base_address(trk_idx,clip_idx,debug=True)

  for i in range(5):
    zcore.coarse_tune_rmw(base_address,1,debug=True)
    sleep(1)

  exit()

