import templeton.handlers
import web
import pickle
import MySQLdb
import ldap
from devicemanagerSUT import DeviceManagerSUT

# URLs go here. "/api/" will be automatically prepended to each.
urls = ( "/checkout/", "CheckoutHandler", "/checkin/", "CheckinHandler",
"/waiu/","WAIUHandler", "/printDB/", "PrintDBHandler"
)

#Puts the device in a state that is good to be worked with via the ADB
#Currently just sets ADB to use TCP/IP instead of USB
def setupDevice(ip):
  dm = DeviceManagerSUT(ip)
  data = dm.adjustADBTransport('ip');
  if "Successfully" in data:
    return True
  return False

#Puts the device in the same state that it started in.
#The major step in this is rebooting the device.
def resetDevice(ip):
  dm = DeviceManagerSUT(ip)
  status = dm.reboot()
  print(status)
  return

#Given a username and password, return the username's name and email.
def ldapQuery(user, password):
  #Initialize ldap using the given username and password.
  ldapConn = ldap.initialize("ldaps://ldap.mozilla.org/")
  username = "mail="+user+",o=com,dc=mozilla"
  ldapConn.protocol_version = ldap.VERSION3
  ldapConn.bind(username, password)

  #Send a search request to LDAP server. Assumption is only one user per email
  result_id = ldapConn.search("dc=mozilla", ldap.SCOPE_SUBTREE, "mail="+user)
  
  try:
    result_type, result_data = ldapConn.result(result_id, 0)
  except ldap.LDAPError, e:
    if e[0]['desc'] == 'Insufficient access':
      return (None,None)

  #Takes the result_data and returns the two pieces needed.
  #LDAP module returns them in a couple layers of array.
  user = result_data[0][1]['cn'][0]
  email = result_data[0][1]['mail'][0]
  return user, email
  


#Finds an available device to use.
#The devices are stored in a MySQL Database table 'devices'
def findUnusedDevice(deviceType, user, password):
  #First, we need to check the LDAP server
  user, email = ldapQuery(user, password)
  #If user is not returned, then we have a bad login.
  if not user:
    return "Bad Username Or Password"
  #Setup DB Connection
  db = MySQLdb.connect(user="tegra",db="TegraPool")
  c = db.cursor();
  #Lock the table, as we don't want people checking them out simultaneously
  c.execute("LOCK TABLE devices WRITE;")
  c.execute("SELECT deviceIP, state FROM devices WHERE state = 'REBOOTED';")
  row = c.fetchone()
  if row:
    c.execute("UPDATE devices SET state = 'CHECKED_OUT', user = '" + user +
              "', email = '"+email+"' WHERE deviceIP = '" + row[0] + "';")
    c.execute("UNLOCK TABLES;")
    c.close()
    db.commit()
    setupDevice(row[0])
    return row[0]
  c.execute("UNLOCK TABLES;");
  c.close()
  db.commit()
  db.close()
  return None

#Finds the device in the device list and sets the user to None
#Returns true if the device was checked out previously.
def makeDeviceAvailable(ip):
  db = MySQLdb.connect(user="tegra",db="TegraPool")
  c = db.cursor();
  c.execute("LOCK TABLE devices WRITE;")
  c.execute("SELECT state FROM devices WHERE deviceIP = '" + ip + "';")
  row = c.fetchone();
  #If device is not in list, or not checked out, return false.
  if not row or row[0] != 'CHECKED_OUT':
    c.execute("UNLOCK TABLES;");
    c.close();
    return False
  #Otherwise, update the device to be Rebooting
  c.execute("UPDATE devices SET state = 'REBOOTING', user = NULL, email = NULL WHERE deviceIP = '" + ip + "';")
  c.execute("UNLOCK TABLES;")
  db.commit()
  c.close()
  db.close()
  resetDevice(ip)
  return True

#Returns a list of device names and IPs that are checked out to that user.
def getUsedList(user):
  db = MySQLdb.connect(user="tegra",db="TegraPool")
  c = db.cursor();
  c.execute("SELECT deviceid, deviceIP FROM devices WHERE email = '" + user + "';")
  result = c.fetchall()
  c.close()
  db.close()
  return result

#Quick method to return the majority of the device table.
def getTable(db):
  c = db.cursor();
  c.execute("SELECT deviceid, deviceIP, state, user, email FROM devices;")
  result = c.fetchall()
  newDict = {}
  c.close()
  return result

#####
# Handler classes go here
#####

#Handles checkout queries. Input is User and DeviceType
#(Currently doesn't handle more than tegra)
class CheckoutHandler(object):
  @templeton.handlers.json_response
  def POST(self):
    postdata = web.input()
    args, body = templeton.handlers.get_request_parms()
    print("User " + postdata["user"] + " Checked out device of type " + postdata["deviceType"])
    newDeviceIP = findUnusedDevice(postdata["deviceType"],
                                   postdata["user"],
                                   postdata["password"])
    if newDeviceIP and "Bad" in newDeviceIP:
      return newDeviceIP
    elif newDeviceIP:
      return "IP = " + newDeviceIP
    else:
      return "No available devices of requested type."

#Handles checkin queries. Input is IP of the device checked out.
#NOTE: Might be weird if IPs are changing.
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

#WAIU stands for WhatAmIUsing
#Handles queries from a user to see what they are using.
class WAIUHandler(object):
  @templeton.handlers.json_response
  def POST(self):
    postdata = web.input()
    args, body = templeton.handlers.get_request_parms()
    print("User " + postdata["user"] + " wants to know what they checked out")
    devices = getUsedList(postdata["user"])
    return "Devices taken out currently: " + str(devices)

#Returns a subset of the database table.
#Done with a dictionary where key is the device name
#Attrs ar IP, State, and User
class PrintDBHandler(object):
  @templeton.handlers.json_response
  def GET(self):
    print("Accessing entire device DB")
    args, body = templeton.handlers.get_request_parms()
    db = MySQLdb.connect(user="tegra",db="TegraPool")
    result = getTable(db)
    responseDict = {}
    for key in result:
      responseDict[key[0]] = (key[1],key[2],key[3],key[4])
    db.close()
    return responseDict 
