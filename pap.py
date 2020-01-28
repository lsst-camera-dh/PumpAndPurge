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
import logging

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

def CCSattachProxy(target):
	""" Improve reliability """
	for i in range(3):
		logging.info( "{}: {}".format(target, i))
		try:
			return CCS.attachProxy(target)
		except RuntimeException as ex:
			logging.error( ex)
			time.sleep(1)
			pass
	raise

thermal = CCSattachProxy("thermal")
vacuum= CCSattachProxy("vacuum")

def getvacuum( ):
	vac = vacuum.sendSynchCommand("CryoVac getValue")
	logging.info("CyroVac getValu returns {} Torr".format(vac))
	if math.isnan(vac):
		raise

	return vac

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
				logging.debug("{} {}".format(acommandtarget,ccsPrxy))
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
				logging.error("Failed to output {}".format(acommandtarget))

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
 	thermal.setPlateTemperature(0, 35)	# cold plate
 	thermal.setPlateTemperature(1, 35)	# cryo plate

#
#	# 0 (off), > 0 (manual - fixed power) or < 0 (auto - fixed temperature)
 	thermal.setTrimHeaterState(0, -1)	# cold plate onon
 	thermal.setTrimHeaterState(1, -1)	# cold plate onon

##2.       Turn on both cryostat housing band heaters and set the band temperature to ~40 C.

	lwrbndhtr("on")
	upperbandhtr("on")
# 3.       Open the Cryostat gate valve.
	vacuum.setNamedSwitchOn("CryoValve",True) #### NEED TO BE TESTED
	logging.info("PriorSteps Open the CryoValve")


def step1( ):
	logging.info("Step 1. Turn on scroll pump")

	# just make sure
	LowerN2Valve("off")
	NitrogenHeater("off")
	NitrogenFlow("off")

	# wail until the pressure gets below 760 Torr
	# this will stops forever if the cryostat is overpressurised. Need to put ScrollPump on in the PriorStep
	vac = 780
	while vac > 760:
		time.sleep(6)
		# not sure why but vacuum.CryoVac canot be used
		vac = getvacuum()

	ScrollPump("on")

def step2( lowpress=1. ):
	logging.info("Step 2. Wait until pressure gets down to {} Torr".format(lowpress))
	# wait until pressure gets down to 100 mTorr
	vac = 760
	while vac > lowpress:
		time.sleep(6)
		# not sure why but vacuum.CryoVac canot be used
		vac = getvacuum()
#		CheckTemp()


def step3( ):
	logging.info("Step 3. Turn off scroll pump")
	ScrollPump("off")

def step4( ):
	logging.info("Step 4. Turn on N2 heater and flow")
	LowerN2Valve("on")
	NitrogenHeater("on")
	NitrogenFlow("on")

def step5( ):
	# wait until pressure gets reached at 760 Torr
	logging.info("Step 5. Turn off N2 heater and flow when pressure gets reached at 760 Torr")
	vac = 0
	while vac < 550:
		time.sleep(6)
		# not sure why but vacuum.CryoVac canot be used
		vac = getvacuum( )
#		CheckTemp()

	NitrogenHeater("off")
	while vac < 750:
		time.sleep(6)
		# not sure why but vacuum.CryoVac canot be used
		vac = getvacuum( )
#		CheckTemp()
	NitrogenFlow("off")
	LowerN2Valve("off")
	
def Cleanup():
	logging.info("Clean up. Turn off heaters and close the valve.")
#
#	# 0 (off), > 0 (manual - fixed power) or < 0 (auto - fixed temperature)
 	thermal.setPlateTemperature(0, 17)	# cold plate
 	thermal.setPlateTemperature(1, 17)	# cryo plate
 	thermal.setTrimHeaterState(0, 0)	# cold plate onon
 	thermal.setTrimHeaterState(1, 0)	# cold plate onon

# 3.       Close the Cryostat gate valve.
	vacuum.setNamedSwitchOn("CryoValve",False) #### NEED TO BE TESTED
	NitrogenHeater("off")
	NitrogenFlow("off")
	LowerN2Valve("off")
	lwrbndhtr("off")
	upperbandhtr("off")


def toggle( string, state ):
	logging.info("Turn {} {}".format(string, state))
	target = string.split("/")
	pduprxy = CCSattachProxy(target[0])
	pduprxy = getattr(pduprxy,target[1])()
	pduprxy = getattr(pduprxy,"forceOutlet{}".format(state.capitalize()))
	pduprxy("{}".format(target[2]))

def lwrbndhtr( state ):
	toggle("pap-pdu/PDU230/lwrbandhtr",state)

def upperbandhtr( state ):
	toggle("pap-pdu/PDU230/upperbandhtr",state)

def ScrollPump( state ):
	toggle("pap-pdu/PDU230/vacuumscrollpump",state)

def NitrogenFlow( state ):
	toggle("pap-pdu/PDU120/nitrogenvalve",state)

def NitrogenHeater( state ):
	toggle("pap-pdu/PDU120/n2heater",state)

def LowerN2Valve( state ):
	toggle("pap-pdu/PDU120/lowern2valve",state)

def CheckTemp( ):
	thermaltemp=Monitor(thermal)
	thermaltemp.GetCurrentValues()
	if thermaltemp.stats(r"CRY-CLP.*")["max"] > 50:
		raise Exception("Hits the cold plate temperature limit")
	if thermaltemp.stats(r"CRY-CYP.*")["max"] > 50:
		raise Exception("Hits the cryo plate temperature limit")

# main statement
def main(N,lowpress):
	try:
		PriorSteps()
		for i in range(N):
			logging.info("{} of {} cycles. Hit Ctrl+C if you want to abort.".format(i+1, N))
			step1()
			step2(lowpress)
			step3()
			step4()
			step5()

	except KeyboardInterrupt:
		raise

	except:
		import traceback
		traceback.print_exc()

	finally:
		Cleanup()

if __name__=="__main__":
	parser = argparse.ArgumentParser(description='A script to do pump and purge')
	parser.add_argument('integers', metavar='N', type=int, default=40,
	    help='an integer for cycle to be done')
	args = parser.parse_args()

	main(args.integers,2.0)
