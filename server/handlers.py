import templeton.handlers
import web
import pickle

# URLs go here. "/api/" will be automatically prepended to each.
urls = ( "/checkout/", "CheckoutHandler", "/checkin/", "CheckinHandler",
"/waiu/","WAIUHandler", "/printDB/", "PrintDBHandler"
)

#Finds an available device to use.
#The devices are stored in a pickle file as a dictionary
# of form IP:(User,Type)
def findUnusedDevice(deviceType, user):
  deviceFile = open("devices.txt", "r+")
  devices = pickle.load(deviceFile)
  for ip in devices.keys():
    if not devices[ip][0] and devices[ip][1] == deviceType:
      devices[ip] = (user, deviceType)
      deviceFile.seek(0,0)
      pickle.dump(devices, deviceFile)
      deviceFile.close();
      return ip
  return None

#Finds the device in the device list and sets the user to None
#Returns true if the device was checked out previously.
def makeDeviceAvailable(ip):
  deviceFile = open("devices.txt", "r+")
  devices = pickle.load(deviceFile)
  #If device is not in list, or not checked out, return false.
  if ip not in devices or devices[ip][0] == None:
    return False
  devices[ip] = (None, devices[ip][1])
  deviceFile.seek(0,0)
  pickle.dump(devices, deviceFile)
  deviceFile.close();
  return True

def getUsedList(user):
  deviceFile = open("devices.txt", "r")
  devices = pickle.load(deviceFile)
  usedDevices = []
  for ip in devices:
    if devices[ip][0] == user:
      usedDevices.append((ip, devices[ip][1]))
  return usedDevices

# Handler classes go here

class CheckoutHandler(object):
  @templeton.handlers.json_response
  def POST(self):
    postdata = web.input()
    args, body = templeton.handlers.get_request_parms()
    print("User " + postdata["user"] + " Checked out device of type " + postdata["deviceType"])
    newDeviceIP = findUnusedDevice(postdata["deviceType"], postdata["user"])
    if newDeviceIP:
      return "IP = " + newDeviceIP
    else:
      return "No available devices of requested type."

class CheckinHandler(object):
  @templeton.handlers.json_response
  def POST(self):
    postdata = web.input()
    args, body = templeton.handlers.get_request_parms()
    print("Device " + postdata["ip"] + " checked in")
    response = makeDeviceAvailable(postdata["ip"])
    if response:
      return "Checkin Successful"
    return "You checked in an IP that wasn't checked out... I would look into that."

class WAIUHandler(object):
  @templeton.handlers.json_response
  def POST(self):
    postdata = web.input()
    args, body = templeton.handlers.get_request_parms()
    print("User " + postdata["user"] + " wants to know what they checked out")
    devices = getUsedList(postdata["user"])
    return "Devices taken out currently: " + str(devices)

class PrintDBHandler(object):
  @templeton.handlers.json_response
  def GET(self):
    print("Accessing entire device DB")
    args, body = templeton.handlers.get_request_parms()
    deviceList = open("devices.txt")
    devices = pickle.load(deviceList)
    return devices
