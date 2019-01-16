#!/usr/bin/env ccs-script
import sys
sys.path.insert(0,"/gpfs/slac/lsst/fs1/g/data/youtsumi/fp-scripts/lib")
from org.lsst.ccs.scripting import CCS, ScriptingTimeoutException
from org.lsst.ccs.bus.states import AlertState
from org.lsst.ccs.messaging import CommandRejectedException
from java.time import Duration
from java.lang import RuntimeException
from ccs import proxies
import re
import math
import time
import argparse


def CCSattachProxy(target):
	""" Improve reliability """
	for i in range(3):
		print( "{}: {}".format(target, i))
		try:
			return CCS.attachProxy(target)
		except RuntimeException as ex:
			print( ex)
			time.sleep(1)
			pass
	raise

thermal = CCSattachProxy("thermal")
vacuum= CCSattachProxy("vacuum")

class Monitor:
	def __init__(self,target,verbose=False):
		self.target=target
		self.result = {}
		self.ignorelist=[]
		self._length = 5
		self.GetCurrentValues(verbose)

	def GetCurrentValues(self,verbose=False):
		""" Keep recent 3 measurements in a dictionary  """
		for acommandtarget in self.target.getChannelNames():
			if acommandtarget in self.ignorelist:
				continue
			try:
				ccsPrxy=self.target
				ccsPrxy = getattr(ccsPrxy,acommandtarget)()
				if verbose:
					print acommandtarget,ccsPrxy
				if self.result.has_key(acommandtarget):
					self.result[acommandtarget].append(
							ccsPrxy.getValue()
						)
					if len(self.result)>=self._length+1:
						self.result[acommandtarget].pop(0)
				else:
					self.result.update({acommandtarget: [ ccsPrxy.getValue() ] * self._length })
			except CommandRejectedException:
				self.ignorelist.append(acommandtarget)
				if verbose:
					print( "Failed to output {}".format(acommandtarget) )

	def Filter( self, regexp ):
		p = re.compile(regexp)
		selected = filter(
			lambda x: True if p.match(x) is not None else False,
			self.result.keys() )
		return dict( [ ( k, self.result[k]) for k in selected ]  )

	def stats( self, regexp ):
		data = self.Filter(regexp)
		latest = [ x[-1] for x in data.values() ]
		N = len(latest)
		total = sum( latest )
		maxv = max( latest )
		minv = min( latest )
		sq = sum( [ x**2 for x in latest ])
		avg = total/N
		std = math.sqrt(sq/N-avg**2)
		median = sorted(latest)[int(N/2)]
		return {
			"regexp": regexp,
			"mean": avg,
			"std": std,
			"median": median,
			"max": maxv,
			"min": minv
			}
		
	def PrintValues(self,verbose=False):
		for k,v in sorted(self.result.items()):
			print k,v


def PriorSteps():
#1.       Turn on cold and cryo plate trim heater. 
#Set cryo plate temperature and cold plate temperature at feedback control. 
#Cryo = 40 C and Cold = 40 C (Martin said that the cold plate can be set at 60 C). 
#                The L3 lens has a upper temperature limit of 40 C.
	thermal.setPlateTemp(0, 40)	# cold plate
	thermal.setPlateTemp(1, 40)	# cryo plate

	# 0 (off), > 0 (manual - fixed power) or < 0 (auto - fixed temperature)
	thermal.setHeaterControl(0, -1)	# cold plate onon
	thermal.setHeaterControl(1, -1)	# cold plate onon

#2.       Turn on both cryostat housing band heaters and set the band temperature to ~40 C.
	thermal.setHeaterPowerEnable(0, 1)
	thermal.setHeaterPowerEnable(1, 1)


	vacuum.setNamedSwitchOn("CryoValve",1) #### NEED TO BE TESTED
# 3.       Open the Cryostat gate valve.


def step1( ):
	ScrollPump("on")

def step2( ):
	# wait until pressure gets down to 100 mTorr
	vac = 760
	time.sleep(20*60)
	while vac > 0.1:
		# not sure why but vacuum.CryoVac canot be used
		vac = vacuum.sendSynchCommand("CryoVac getValue")
		print("CyroVac getValu returns {} Torr".format(vac))
		time.sleep(60)
		CheckTemp()


def step3( ):
	print("Step 3. Turn off scroll pump")
	# Don't I need to close the valve here?
	ScrollPump("off")

def step4( ):
	print("Step 4. Turn on N2 heater and flow")
	NitrogenHeater("on")
	NitrogenFlow("on")

def step5( ):
	# wait until pressure gets reached at 760 Torr
	print("Step 5. Turn off N2 heater and flow when pressure gets reached at 760 Torr")
	vac = 760
	while vac < 760:
		# not sure why but vacuum.CryoVac canot be used
		vac = vacuum.sendSynchCommand("CryoVac getValue")
		print("CyroVac getValu returns {} Torr".format(vac))
		time.sleep(60)
		CheckTemp()

	NitrogenHeater("off")
	time.sleep(120)
	NitrogenFlow("off")
	
def Cleanup():
	print("Clean up. Turn off heaters and close the valve.")

	# 0 (off), > 0 (manual - fixed power) or < 0 (auto - fixed temperature)
	thermal.setHeaterControl(0, 0)	# cold plate onon
	thermal.setHeaterControl(1, 0)	# cold plate onon

	thermal.setHeaterPowerEnable(0, 0)
	thermal.setHeaterPowerEnable(1, 0)

# 3.       Close the Cryostat gate valve.
	vacuum.setNamedSwitchOn("CryoValve",0) #### NEED TO BE TESTED

def toggle( string, state ):
	print("Turn {} {}".format(string, state))
	target = string.split("/")
	pduprxy = CCSattachProxy(target[0])
	pduprxy = getattr(pduprxy,target[1])()
	pduprxy = getattr(pduprxy,"forceOutlet{}".format(state.capitalize()))
	pduprxy("{}".format(target[2]))

def ScrollPump( state ):
	toggle("pap-pdu/PDU230/vacuumscrollpump",state)

def NitrogenFlow( state ):
	toggle("pap-pdu/PDU120/nitrogenvalve",state)

def NitrogenHeater( state ):
	toggle("pap-pdu/PDU120/n2heater",state)


def CheckTemp( ):
	thermaltemp.GetCurrentValues()
	if thermaltemp.stats(r"CRY-CLP.*")["max"] > 50:
		raise Exception("Hits the cold plate temperature limit")
	if thermaltemp.stats(r"CRY-CYP.*")["max"] > 50:
		raise Exception("Hits the cryo plate temperature limit")



# main statement
def main(N):
	try:
		thermaltemp=Monitor(thermal)
		vacuumvalue=Monitor(vacuum)

		PriorSteps()
		for i in range(N):
			print("{} of {} cycles. Hit Ctrl+C if you want to abort.".format(i+1, N))
			step1()
			step2()
			step3()
			step4()
			step5()

	except:
		pass

	finally:
		Cleanup()


if __name__=="__main__":
	parser = argparse.ArgumentParser(description='A script to do pump and purge')
	parser.add_argument('integers', metavar='N', type=int, default=40,
			    help='an integer for cycle to be done')
	args = parser.parse_args()
#	main(args.integers)
