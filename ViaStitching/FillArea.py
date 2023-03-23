#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#  FillArea.py
#
#  Copyright 2017 JS Reynaud <js.reynaud@gmail.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

from __future__ import print_function
from pcbnew import *
import sys
import tempfile
import shutil
import os
import random
import pprint
import wx
from inspect import currentframe, getframeinfo
import time


def wxPrint(msg):
    wx.LogMessage(msg)


#
if sys.version[0] == '2':  # maui
    None
else:
    xrange = range


"""
#  This script fills all areas of a specific net with Vias (Via Stitching)
#
#
# Usage in pcbnew's python console:
#  First you neet to copy this file (named FillArea.py) in your kicad_plugins
# directory (~/.kicad_plugins/ on Linux)
# Launch pcbnew and open python console (last entry of Tools menu)
# Then enter the following line (one by one, Hit enter after each)
import FillArea
FillArea.FillArea().Run()


# Other example:
# You can add modifications to parameters by adding functions calls:
FillArea.FillArea().SetDebug().SetNetname("GND").SetStepMM(1.27).SetSizeMM(0.6).SetDrillMM(0.3).SetClearanceMM(0.2).Run()

# with
# SetDebug: Activate debug mode (print evolution of the board in ascii art)
# SetNetname: Change the netname to consider for the filling
# (default is /GND or fallback to GND)
# SetStepMM: Change step between Via (in mm)
# SetSizeMM: Change Via copper size (in mm)
# SetDrillMM: Change Via drill hole size (in mm)
# SetClearanceMM: Change clearance for Via (in mm)

#  You can also use it in command line. In this case, the first parameter is
# the pcb file path. Default options are applied.

"""


class ViaObject:

    """
    ViaObject holds all information of a single Via
    """

    def __init__(self, x, y, pos_x, pos_y):
        self.X = x
        self.Y = y
        self.PosX = pos_x
        self.PosY = pos_y


class ViaStitchSettings:
    """
    Contains all settings for the run, can be passed around as configuration tables
    """
    def __init__(self):
        # Size of the via (diameter of copper)
        self._size_mm = 0.8 # mm
        # Size of the drill (diameter)
        self._drill_mm = 0.4 # mm
        self._pattern = "grid"
        self._step_mm = 2.54
        # Isolation between via and other elements
        # ie: radius from the border of the via
        self._clearance_mm = 0.2
        self._netname = "GND"
        self._layer = "F.Cu"
        self._only_selected_area = False
        self._delete_vias = False
        self._netname = "GND"
        self._random = False
        self._star = False

        self.parent_area = None
        self.pcb_group = None
        self.target_net = None


class FileSettings:
    def __init__(self, filename=None):
        self._filename = filename
        self.tmp_dir = None


class FillArea:

    """
    Automaticaly add via on area where there are no track/existing via,
    pads and keepout areas
    """

    REASON_OK = 0
    REASON_NO_SIGNAL = 1
    REASON_OTHER_SIGNAL = 2
    REASON_KEEPOUT = 3
    REASON_TRACK = 4
    REASON_PAD = 5
    REASON_DRAWING = 6
    REASON_STEP = 7

    @property
    def size_mm(self):
        return self.settings.size_mm

    @size_mm.setter:
        def size_mm(self, value):
            self.settings._size_mm = value
        self._drill_mm = 0.4 # mm
        self._pattern = "grid"
        self._step_mm = 2.54
        self._clearance_mm = 0.2
        self._netname = "GND"
        self._layer = "F.Cu"
        self._only_selected_area = False
        self._delete_vias = False
        self._netname = "GND"
        self._random = False
        self._star = False

    def __init__(self, filename=None, viasettings=None):
        self.settings = viasettings
        if viasettings is None:
            self.settings = ViaStitchSettings()

        self.filename = None
        self.clearance = 0
        # Net name to use
        self.SetPCB(GetBoard())
        # Set the filename
        self.SetFile(filename)
        # Step between via
        self.SetStepMM(2.54)
        # Size of the via (diameter of copper)
        self.SetSizeMM(0.46)
        # Size of the drill (diameter)
        self.SetDrillMM(0.20)
        # Isolation between via and other elements
        # ie: radius from the border of the via
        self.SetClearanceMM(0.2)
        self.only_selected_area = False
        self.delete_vias = False
        if self.pcb is not None:
            for lnet in ["GND", "/GND"]:
                if self.pcb.FindNet(lnet) is not None:
                    self.SetNetname(lnet)
                    break
        self.netname = None
        self.debug = False
        self.random = False
        self.star = False
        if self.netname is None:
            self.SetNetname("GND")

        self.tmp_dir = None
        self.parent_area = None
        self.pcb_group = None
        self.target_net = None

    def SetFile(self, filename):
        self.filename = filename
        if self.filename:
            self.SetPCB(LoadBoard(self.filename))

    def SetDebug(self):
        wxPrint("Set debug")
        self.debug = True
        return self

    def SetRandom(self, r):
        random.seed()
        self.random = r
        return self

    def SetStar(self):
        self.star = True
        return self

    def SetPCB(self, pcb):
        self.pcb = pcb
        if self.pcb is not None:
            self.pcb.BuildListOfNets()
        return self

    def SetNetname(self, netname):
        self.netname = netname  # .upper()
        # wx.LogMessage(self.netname)
        return self

    def SetStepMM(self, s):
        self.step = float(FromMM(s))
        return self

    def SetSizeMM(self, s):
        self.size = float(FromMM(s))
        return self

    def SetDrillMM(self, s):
        self.drill = float(FromMM(s))
        return self

    def OnlyOnSelectedArea(self):
        self.only_selected_area = True
        return self

    def DeleteVias(self):
        self.delete_vias = True
        return self

    def SetClearanceMM(self, s):
        self.clearance = float(FromMM(s))
        return self

    def GetReasonSymbol(self, reason):
        if isinstance(reason, ViaObject):
            return "X"
        if reason == self.REASON_NO_SIGNAL:
            return " "
        if reason == self.REASON_OTHER_SIGNAL:
            return "O"
        if reason == self.REASON_KEEPOUT:
            return "K"
        if reason == self.REASON_TRACK:
            return "T"
        if reason == self.REASON_PAD:
            return "P"
        if reason == self.REASON_DRAWING:
            return "D"
        if reason == self.REASON_STEP:
            return "-"

        return str(reason)

    def PrintRect(self, rectangle):
        """debuging tool
        Print board in ascii art
        """
        print("_" * (len(rectangle)+2))
        for y in range(len(rectangle[0])):
            print("|", end='')
            for x in range(len(rectangle)):
                print("%s" % self.GetReasonSymbol(rectangle[x][y]), end='')
            print("|")
        print("_" * (len(rectangle)+2))
        print('''
OK           = 'X'
NO_SIGNAL    = ' '
OTHER_SIGNAL = 'O'
KEEPOUT      = 'K'
TRACK        = 'T'
PAD          = 'P'
DRAWING      = 'D'
STEP         = '-'
''')

    def AddVia(self, position, x, y):
        if self.parent_area:
            m = PCB_VIA(self.parent_area)
            m.SetPosition(position)
            if self.target_net is None:
                self.target_net = self.pcb.FindNet(self.netname)
            m.SetNet(self.target_net)
            m.SetViaType(VIATYPE_THROUGH)
            m.SetDrill(int(self.drill))
            m.SetWidth(int(self.size))
            m.SetIsFree(True)
            # again possible to mark via as own since no timestamp_t binding kicad v5.1.4
            # m.SetParentGroup(self.parent_group)
            # wx.LogMessage('adding vias')
            self.pcb.Add(m)
            self.pcb_group.AddItem(m)
        else:
            wxPrint("\nUnable to find a valid parent area (zone)")

    def RefillBoardAreas(self):
        for i in range(self.pcb.GetAreaCount()):
            area = self.pcb.GetArea(i)
            area.UnFill()
        filler = ZONE_FILLER(self.pcb)
        filler.Fill(self.pcb.Zones())

    def CheckViaInAllAreas(self, via, all_areas):
        '''
        Checks if an existing Via collides with another area
        '''
        # Enum all area
        for area in all_areas:
            area_layer = area.GetLayer()
            area_clearance = area.GetLocalClearance()
            area_priority = area.GetPriority()
            is_keepout_area = False  # area.GetIsKeepout()
            is_target_net = (area.GetNetname() == self.netname)  # (area.GetNetname().upper() == self.netname)
            # wx.LogMessage(area.GetNetname()) #wx.LogMessage(area.GetNetname().upper())

            if (not is_target_net):                                                         # Only process areas that are not in the target net
                # Offset is half the size of the via plus the clearance of the via or the area
                offset = max(self.clearance, area_clearance) + self.size / 2
                for dx in [-offset, offset]:
                    # All 4 corners of the via are testet (upper, lower, left, right) but not the center
                    for dy in [-offset, offset]:
                        point_to_test = wxPoint(via.PosX + dx, via.PosY + dy)

                        hit_test_area = area.HitTestFilledArea(area.GetLayer(), point_to_test)             # Collides with a filled area
                        hit_test_edge = area.HitTestForEdge(point_to_test, 1)              # Collides with an edge/corner
                        try:
                            hit_test_zone = area.HitTestInsideZone(point_to_test)         # Is inside a zone (e.g. KeepOut)
                        except:
                            hit_test_zone = False
                            wxPrint('exception: missing HitTestInsideZone: To Be Fixed')
                            # hit_test_zone   = area.HitTest(point_to_test)              # Is inside a zone (e.g. KeepOut) kicad nightly 5.99
                        if is_keepout_area and (hit_test_area or hit_test_edge or hit_test_zone):
                            return self.REASON_KEEPOUT                                      # Collides with keepout

                        elif (hit_test_area or hit_test_edge):
                            # Collides with another signal (e.g. on another layer)
                            return self.REASON_OTHER_SIGNAL

                        elif hit_test_zone:
                            # Check if the zone is higher priority than other zones of the target net in the same point
                            # target_areas_on_same_layer = filter(lambda x: ((x.GetPriority() > area_priority) and (x.GetLayer() == area_layer) and (x.GetNetname().upper() == self.netname)), all_areas)
                            target_areas_on_same_layer = filter(lambda x: ((x.GetPriority() > area_priority) and (
                                x.GetLayer() == area_layer) and (x.GetNetname() == self.netname)), all_areas)
                            for area_with_higher_priority in target_areas_on_same_layer:
                                if area_with_higher_priority.HitTestInsideZone(point_to_test):
                                    break                                                   # Area of target net has higher priority on this layer
                            else:
                                # Collides with another signal (e.g. on another layer)
                                return self.REASON_OTHER_SIGNAL

        return self.REASON_OK

    def ClearViaInStepSize(self, rectangle, x, y, distance):
        '''
        Stepsize==0
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O
            O O O O O O O O O

        Standard
            O   O   O   O   O

            O   O   O   O   O

            O   O   O   O   O

            O   O   O   O   O

        Star
            O   O   O   O   O
              O   O   O   O
            O   O   O   O   O
              O   O   O   O
            O   O   O   O   O
              O   O   O   O
            O   O   O   O   O
        '''
        for x_pos in range(x-distance, x+distance+1):
            if (x_pos >= 0) and (x_pos < len(rectangle)):
                distance_y = distance-abs(x-x_pos) if self.star else distance       # Star or Standard shape
                for y_pos in range(y-distance_y, y+distance_y+1):
                    if (y_pos >= 0) and (y_pos < len(rectangle[0])):
                        if (x_pos == x) and (y_pos == y):
                            continue
                        rectangle[x_pos][y_pos] = self.REASON_STEP

    def Run(self):

        VIA_GROUP_NAME = "ViaStitching {}".format(self.netname)

        if self.debug:
            print("Enumerate groups")
        for i in self.pcb.Groups():
            if i.GetName() == VIA_GROUP_NAME:
                if self.debug:
                    print("Group {} Found !".format(VIA_GROUP_NAME))
                self.pcb_group = i

        """
        Launch the process
        """
        if self.delete_vias:
            # timestmap again available
            # target_tracks = filter(lambda x: (x.GetNetname().upper() == self.netname), self.pcb.GetTracks())
            wx.MessageBox(
                "To delete vias:\n - select one of the generated via to select the group of vias named {}\n - hit delete key\n - That's all !".format(VIA_GROUP_NAME), "Information")
            return                                          # no need to run the rest of logic

        if self.pcb_group is None:
            self.pcb_group = PCB_GROUP(None)
            self.pcb_group.SetName(VIA_GROUP_NAME)
            self.pcb.Add(self.pcb_group)

        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        target_tracks = self.pcb.GetTracks()
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))

        lboard = self.pcb.ComputeBoundingBox(False)
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        origin = lboard.GetPosition()
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))

        # Create an initial rectangle: all is set to "REASON_NO_SIGNAL"
        # get a margin to avoid out of range
        l_clearance = self.clearance + self.size
        if l_clearance < self.step:
            l_clearance = self.step

        x_limit = int((lboard.GetWidth() + l_clearance) / l_clearance) + 1
        y_limit = int((lboard.GetHeight() + l_clearance) / l_clearance) + 1
        if self.debug:
            print("l_clearance : {}; step : {}; size: {}; clearance: {}; x/y_limit ({} {}),board size : {} {}".format(l_clearance,
                                                                                                                      self.step,
                                                                                                                      self.size,
                                                                                                                      self.clearance,
                                                                                                                      x_limit,
                                                                                                                      y_limit,
                                                                                                                      lboard.GetWidth(),
                                                                                                                      lboard.GetHeight()))
        rectangle = [[self.REASON_NO_SIGNAL]*y_limit for i in xrange(x_limit)]

        if self.debug:
            print("\nInitial rectangle:")
            self.PrintRect(rectangle)

        all_pads = self.pcb.GetPads()
        all_tracks = self.pcb.GetTracks()
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        try:
            all_drawings = filter(lambda x: x.GetClass() == 'PTEXT' and self.pcb.GetLayerID(
                x.GetLayerName()) in (F_Cu, B_Cu), self.pcb.DrawingsList())
        except:
            all_drawings = filter(lambda x: x.GetClass() == 'PTEXT' and self.pcb.GetLayerID(
                x.GetLayerName()) in (F_Cu, B_Cu), self.pcb.Drawings())
            # wxPrint("exception on missing BOARD.DrawingsList")
        all_areas = [self.pcb.GetArea(i) for i in xrange(self.pcb.GetAreaCount())]
        # target_areas    = filter(lambda x: (x.GetNetname().upper() == self.netname), all_areas)         # KeepOuts are filtered because they have no name
        # KeepOuts are filtered because they have no name
        target_areas = filter(lambda x: (x.GetNetname() == self.netname), all_areas)

        via_list = []       # Create a list of existing vias => faster than scanning through the whole rectangle
        max_target_area_clearance = 0

        # Enum all target areas (Search possible positions for vias on the target net)
        for area in target_areas:
            if self.debug:
                print("%s: Line %u" % (time.time(), currentframe().f_lineno))
            wxPrint("Processing Target Area: %s, LayerName: %s..." % (area.GetNetname(), area.GetLayerName()))
            if self.parent_area is None:
                self.parent_area = area
            is_selected_area = area.IsSelected()
            area_clearance = area.GetLocalClearance()
            if max_target_area_clearance < area_clearance:
                max_target_area_clearance = area_clearance

            if (not self.only_selected_area) or (self.only_selected_area and is_selected_area):         # All areas or only the selected area
                # Check every possible point in the virtual coordinate system
                if self.debug:
                    print("%s: Line %u" % (time.time(), currentframe().f_lineno))
                for x in xrange(len(rectangle)):
                    if x % 10 == 0:
                        if self.debug:
                            print("%s: Line %u (x=%s;%s)" % (time.time(), currentframe().f_lineno, x, len(rectangle)))
                    for y in xrange(len(rectangle[0])):
                        # No other "target area" found yet => go on with processing
                        if rectangle[x][y] == self.REASON_NO_SIGNAL:
                            current_x = origin.x + (x * l_clearance)                                    # Center of the via
                            current_y = origin.y + (y * l_clearance)

                            test_result = True                                                          # Start with true, if a check fails, it is set to false

                            # Offset is half the size of the via plus the clearance of the via or the area
                            offset = 0  # Use an exact zone match
                            point_to_test = wxPoint(int(current_x), int(current_y))
                            hit_test_area = area.HitTestFilledArea(
                                area.GetLayer(), point_to_test, int(offset))             # Collides with a filled area
                            # Collides with an edge/corner
                            hit_test_edge = area.HitTestForEdge(point_to_test, int(max(area_clearance, offset)))
                            # test_result only remains true if the via is inside an area and not on an edge
                            test_result = (hit_test_area and not hit_test_edge)

                            if test_result:
                                # Create a via object with information about the via and place it in the rectangle
                                via_obj = ViaObject(x=x, y=y, pos_x=current_x, pos_y=current_y)
                                rectangle[x][y] = via_obj
                                via_list.append(via_obj)

        if self.debug:
            print("\nPost target areas:")
            self.PrintRect(rectangle)

        # Enum all vias
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        wxPrint("Processing all vias of target area...")
        for via in via_list:
            reason = self.CheckViaInAllAreas(via, all_areas)
            if reason != self.REASON_OK:
                rectangle[via.X][via.Y] = reason

        if self.debug:
            print("\nPost areas:")
            self.PrintRect(rectangle)

        # Same job with all pads => all pads on all layers
        wxPrint("Processing all pads...")
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        for pad in all_pads:
            local_offset = max(pad.GetLocalClearance(), self.clearance, max_target_area_clearance) + (self.size / 2)
            max_size = max(pad.GetSize().x, pad.GetSize().y)

            start_x = int(floor(((pad.GetPosition().x - (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))
            stop_x = int(ceil(((pad.GetPosition().x + (max_size / 2.0 + local_offset)) - origin.x) / l_clearance))

            start_y = int(floor(((pad.GetPosition().y - (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))
            stop_y = int(ceil(((pad.GetPosition().y + (max_size / 2.0 + local_offset)) - origin.y) / l_clearance))

            for x in range(start_x, stop_x + 1):
                for y in range(start_y, stop_y + 1):
                    try:
                        if isinstance(rectangle[x][y], ViaObject):
                            start_rect = wxPoint(origin.x + (l_clearance * x) - local_offset,
                                                 origin.y + (l_clearance * y) - local_offset)
                            size_rect = wxSize(2 * local_offset, 2 * local_offset)
                            if pad.HitTest(EDA_RECT(start_rect, size_rect), False):
                                rectangle[x][y] = self.REASON_PAD
                            else:
                                # Hit test doesn't handle large pads. This following should fix that.
                                m = PCB_VIA(self.parent_area)
                                m.SetPosition(wxPoint(origin.x + (l_clearance * x), origin.y + (l_clearance * y)))
                                m.SetNet(self.target_net)
                                m.SetViaType(VIATYPE_THROUGH)
                                m.SetDrill(int(self.drill))
                                m.SetWidth(int(self.size))
                                if pad.GetEffectivePolygon().Collide(m.GetEffectiveShape()):
                                    rectangle[x][y] = self.REASON_PAD

                    except:
                        wxPrint("exception on Processing all pads...")
        if self.debug:
            print("\nPost pads:")
            self.PrintRect(rectangle)

        # Same job with tracks => all tracks on all layers
        wxPrint("Processing all tracks...")
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        for track in all_tracks:
            start_x = track.GetStart().x
            start_y = track.GetStart().y

            stop_x = track.GetEnd().x
            stop_y = track.GetEnd().y

            if start_x > stop_x:
                d = stop_x
                stop_x = start_x
                start_x = d

            if start_y > stop_y:
                d = stop_y
                stop_y = start_y
                start_y = d

            osx = start_x
            osy = start_y
            opx = stop_x
            opy = stop_y

            clearance = max(track.GetLocalClearance(""), self.clearance, max_target_area_clearance) + \
                (self.size / 2) + (track.GetWidth() / 2)

            start_x = int(floor(((start_x - clearance) - origin.x) / l_clearance))
            stop_x = int(ceil(((stop_x + clearance) - origin.x) / l_clearance))

            start_y = int(floor(((start_y - clearance) - origin.y) / l_clearance))
            stop_y = int(ceil(((stop_y + clearance) - origin.y) / l_clearance))

            for x in range(start_x, stop_x + 1):
                for y in range(start_y, stop_y + 1):
                    try:
                        if isinstance(rectangle[x][y], ViaObject):
                            start_rect = wxPoint(origin.x + (l_clearance * x) - clearance,
                                                 origin.y + (l_clearance * y) - clearance)
                            size_rect = wxSize(2 * clearance, 2 * clearance)
                            if track.HitTest(EDA_RECT(start_rect, size_rect), False):
                                rectangle[x][y] = self.REASON_TRACK
                    except:
                        wxPrint("exception on Processing all tracks...")

        if self.debug:
            print("\nPost tracks:")
            self.PrintRect(rectangle)

        # Same job with existing text
        wxPrint("Processing all existing drawings...")
        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        for draw in all_drawings:
            inter = float(self.clearance + self.size) / 2
            bbox = draw.GetBoundingBox()

            start_x = int(floor(((bbox.GetPosition().x - inter) - origin.x) / l_clearance))
            stop_x = int(ceil(((bbox.GetPosition().x + (bbox.GetSize().x + inter)) - origin.x) / l_clearance))

            start_y = int(floor(((bbox.GetPosition().y - inter) - origin.y) / l_clearance))
            stop_y = int(ceil(((bbox.GetPosition().y + (bbox.GetSize().y + inter)) - origin.y) / l_clearance))

            for x in range(start_x, stop_x):
                for y in range(start_y, stop_y):
                    rectangle[x][y] = self.REASON_DRAWING

        if self.debug:
            print("Post Drawnings:")
            self.PrintRect(rectangle)

        clear_distance = 0
        if self.step != 0.0 and self.star:
            # How much "via steps" should be removed around a via (round up)
            clear_distance = int((self.step+l_clearance) / l_clearance)

        via_placed = 0
        for x in xrange(len(rectangle)):
            for y in xrange(len(rectangle[0])):
                if isinstance(rectangle[x][y], ViaObject):
                    if clear_distance:
                        self.ClearViaInStepSize(rectangle, x, y, clear_distance)

                    via = rectangle[x][y]
                    ran_x = 0
                    ran_y = 0

                    if self.random:
                        ran_x = (random.random() * l_clearance / 2.0) - (l_clearance / 4.0)
                        ran_y = (random.random() * l_clearance / 2.0) - (l_clearance / 4.0)

                    self.AddVia(wxPoint(via.PosX + ran_x, via.PosY + ran_y), via.X, via.Y)
                    via_placed += 1

        if self.debug:
            print("\nFinal result:")
            self.PrintRect(rectangle)

        if self.debug:
            print("%s: Line %u" % (time.time(), currentframe().f_lineno))
        self.RefillBoardAreas()

        if self.filename:
            self.pcb.Save(self.filename)
        msg = "{:d} vias placed\n".format(via_placed)
        wxPrint(msg+"Done!")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: %s <KiCad pcb filename>" % sys.argv[0])
    else:
        import sys
        FillArea(sys.argv[1]).SetDebug().Run()
