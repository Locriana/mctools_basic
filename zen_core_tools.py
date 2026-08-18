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

    # The SysEx address top byte is a layer selector, not just a namespace tag.
    # Probing the same base address under different top bytes returns different data:
    #   0x10 — project name (single block at 0x10000000, 16 bytes, ASCII space-padded)
    #   0x20 — clip/scene names (per-clip 8x16 grid, 12 bytes each, ASCII space-padded)
    #   0x30 — tone names + tone params (the only layer community tools previously used)
    #   0x40 — project/system metadata (tempo, time signature, etc.)
    self.layer_tone = 0x30
    self.layer_clip = 0x20
    self.layer_project = 0x10
    self.layer_system = 0x40

    # Name field sizes (verified via live RQ1 probe on MC-101)
    self.clip_name_size = 12
    self.project_name_size = 16

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

  # --- 4-layer address model ---
  # The top byte of the SysEx address selects a data layer at the same base.
  # This means clip/scene names and project names are readable/writable over SysEx
  # without the .mpj file — enabling full project backup/restore over USB MIDI.
  #
  # Verified live on MC-101 (2026-08-16) via read-only RQ1 probes and DT1 writes.
  # See: https://github.com/soobrosa/mc101-firmware-re — REPORT.md §12.4

  def _swap_layer(self, address, layer):
    """Replace the top byte of an address with the given layer tag."""
    return (address & 0x00FFFFFF) | (layer << 24)

  def clip_name_read(self, track_idx, clip_idx, debug=False):
    """Read the clip/scene name from the 0x20 layer.
    Returns a string (up to 12 chars, space-padded)."""
    base = self.get_base_address(track_idx, clip_idx)
    addr = self._swap_layer(base, self.layer_clip)
    if debug: print(f'clip_name_read: addr=0x{addr:08X}')
    rx = self.comm.roland_request(addr, self.clip_name_size, debug=debug)
    if not rx:
      return ''
    name = ''.join(chr(b) for b in rx if 0x20 <= b < 0x7F).rstrip()
    if debug: print(f'clip_name_read: "{name}"')
    return name

  def clip_name_write(self, track_idx, clip_idx, name, debug=False):
    """Write a clip/scene name to the 0x20 layer.
    Name is padded to 12 bytes with spaces. DT1 writes are not acknowledged
    by the device but are verifiable by RQ1 read-back after ~300ms."""
    base = self.get_base_address(track_idx, clip_idx)
    addr = self._swap_layer(base, self.layer_clip)
    # pad to field size with spaces (0x20)
    name_bytes = name[:self.clip_name_size].encode('ascii', 'replace')
    name_bytes = name_bytes.ljust(self.clip_name_size, b' ')
    tx = list(name_bytes)
    if debug: print(f'clip_name_write: addr=0x{addr:08X}, data={tx}')
    self.comm.roland_set(addr, tx, debug=debug)

  def project_name_read(self, debug=False):
    """Read the project name from the 0x10 layer.
    Returns a string (up to 16 chars, space-padded)."""
    addr = 0x10000000
    if debug: print(f'project_name_read: addr=0x{addr:08X}')
    rx = self.comm.roland_request(addr, self.project_name_size, debug=debug)
    if not rx:
      return ''
    name = ''.join(chr(b) for b in rx if 0x20 <= b < 0x7F).rstrip()
    if debug: print(f'project_name_read: "{name}"')
    return name

  def project_name_write(self, name, debug=False):
    """Write the project name to the 0x10 layer.
    Name is padded to 16 bytes with spaces."""
    addr = 0x10000000
    name_bytes = name[:self.project_name_size].encode('ascii', 'replace')
    name_bytes = name_bytes.ljust(self.project_name_size, b' ')
    tx = list(name_bytes)
    if debug: print(f'project_name_write: addr=0x{addr:08X}, data={tx}')
    self.comm.roland_set(addr, tx, debug=debug)

  def disp_map(self):
    print(f"Zen-Core memory map for tone tracks")
    for trk_idx in range(0,8):
      print(f"track: {trk_idx+1} sound @ addr={self.get_base_address(trk_idx):08X}")
      for clip_idx in range(0,16):
        print(f"    clip: {clip_idx+1} @ addr={self.get_base_address(trk_idx,clip_idx):08X}")

  def disp_clip_grid(self):
    """Print the full 8x16 clip/scene name grid from the 0x20 layer."""
    print(f"Clip/scene name grid (0x20 layer):")
    for trk_idx in range(0,8):
      print(f"  Track {trk_idx+1}:")
      for clip_idx in range(0,16):
        name = self.clip_name_read(trk_idx, clip_idx)
        if name:
          print(f"    clip {clip_idx+1:2d}: \"{name}\"")

if __name__ == "__main__":
  midi = MidiIf(iface='alsa')
  # midi = MidiIf(iface='mido')
  comm = SysExComm(midi)
  zcore = ZenCoreTools(comm)

  # Print project name
  print(f"Project: \"{zcore.project_name_read(debug=True)}\"")

  # Print full clip grid
  zcore.disp_clip_grid()

  exit()

