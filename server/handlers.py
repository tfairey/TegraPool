import templeton.handlers
import web
import MySQLdb
import ldap
import re
import shutil
import subprocess 
import os
import stat
from ftplib import FTP
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
  safeFiles = ["Android",".android_secure","LOST.DIR"]
  dm = DeviceManagerSUT(ip)
  doomedFiles = dm.listFiles('/mnt/sdcard/')
  for fileName in doomedFiles:
    if fileName not in safeFiles:
      print "DELETING " + fileName
      if dm.dirExists('/mnt/sdcard/'+fileName):
        dm.removeDir('/mnt/sdcard/'+fileName)
      else:
        dm.removeFile('/mnt/sdcard/'+fileName)
  status = dm.reboot()
  print(status)
  return

#Given a username and password, return the username's name and email.
def ldapQuery(user, password):
  #Initialize ldap using the given username and password.
  ldapConn = ldap.initialize("ldap://mv-ns.mv.mozilla.com/")
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

#This is the function which, if someone is going remote, will set up a quick temporary account for them.
def initUser(user,ftpSite, ip):
  username = user[:user.find('@')]
  #If they don't already have an account, create one for them.
  if not os.access('/Users/'+username, os.F_OK):
    os.makedirs('/Users/'+username+'/')
    #subprocess.call(["sudo", "mkdir", "/Users/"+username])
    subprocess.call(["sudo", "dscl",".","create","/Users/"+username])
    subprocess.call(["sudo", "dscl",".","create","/Users/"+username, "PrimateGroupID", "21"])
    subprocess.call(["sudo", "dscl",".","create","/Users/"+username, "UniqueID", "999"])
    subprocess.call(["sudo", "dscl",".","passwd","/Users/"+username, "giveMEtegra"])
    subprocess.call(["sudo", "dscl",".","create","/Users/"+username, "NFSHomeDirectory", "/Users/"+username])
    subprocess.call(["sudo", "chmod","0777", "/Users/"+username])
   
  #Go to the FTP Site and collect the APK and ZIP files.
  ftpDir = ftpSite[ftpSite.find('/pub/'):]
  print "ftpDir = " + str(ftpDir)
  #Make sure to get back to the current directory after this function so that there are no issues later
  currDir = os.getcwd()
  os.chdir('/Users/' + username)
  ftp = FTP('ftp.mozilla.org');
  ftp.login();
  ftp.cwd(ftpDir)
  dir = ftp.nlst()
  print "Dir = " + str(dir)
  apkFile = None
  tests = None
  for fileName in dir:
    if ".apk" in fileName:
      apkFile = fileName
      break
  for fileName in dir:
    if ".tests.zip" in fileName:
      tests = fileName
      break
  ftp.sendcmd('PASV')

  #At this point, all of the file names are created.
  fennecFile = "fennec"
  testsFile = "tests.zip"
  mochiFileName = "runMochiRemote.sh"
  refFileName = "runRefRemote.sh"
  talosFileName = "runTalosRemote.sh"
  talosConfigFile = "tpan.yml"
  #Because there could be alternate builds on alternate devices, we add the ip to the name for everything past the first one. 
  if os.access(fennecFile+".apk", os.F_OK):
    fennecFile += ip.replace(".","");
    testsFile += "."+ip;
    mochiFileName += "."+ip;
    refFileName += "."+ip;
    talosFileName += "."+ip;
    talosConfigFile += "."+ip;
  fennecFile+=".apk"
  ftp.retrbinary('retr ' + apkFile, open(fennecFile, 'wb').write)
  ftp.retrbinary('retr ' + tests, open(testsFile, 'wb').write)
  #Create a 'unique' indentifying port that will only be used for this device.
  IPaddr = ip.split('.')
  uniqueNumber = str(10000+int(IPaddr[2])*1000+int(IPaddr[3]))
  #Create the scripts for each of the test types.
  mochiTestScript = open(mochiFileName, "w")
  mochiTestScript.write("unzip "+testsFile+"\nadb disconnect\nadb connect "+ip+"\nadb uninstall org.mozilla.fennec\nadb install "+fennecFile+"\npython mochitest/runtestsremote.py --deviceIP="+ip+" --devicePort=20701 --appname=org.mozilla.fennec --xre-path=/objdir/dist/bin --utility-path=/objdir/dist/bin --http-port="+uniqueNumber);
  mochiTestScript.close();
  talosTestScript = open(talosFileName, "w")
  talosTestScript.write("adb disconnect\nadb connect "+ip+"\nadb uninstall org.mozilla.fennec\nadb install "+fennecFile+"\ncd /talos\npython remotePerfConfigurator.py -v -e org.mozilla.fennec --activeTests tpan --resultsServer '' --resultsLink '' --output ~/"+talosConfigFile+" --remoteDevice "+ip+" --webServer 10.250.2.108\npython run_tests.py -d -n ~/"+talosConfigFile+"\ncd ~");
  talosTestScript.close();
  refTestScript = open(refFileName, "w")
  refTestScript.write("unzip "+testsFile+"\nadb disconnect\nadb connect "+ip+"\nadb uninstall org.mozilla.fennec\nadb install "+fennecFile+"\npython reftest/remotereftest.py --deviceIP="+ip+" --appname=org.mozilla.fennec --xre-path=/objdir/dist/bin --utility-path=/objdir/dist/bin --http-port="+uniqueNumber+" --ignore-window-size reftest/tests/layout/reftests/reftest-sanity/reftest.list");
  refTestScript.close();
  #Make the three scripts totally readable and runnable.
  os.chmod(mochiFileName, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO);
  os.chmod(talosFileName, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO);
  os.chmod(refFileName, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO);
  #Return to the old directory. Don't get stuck in a directory that will be destroyed
  os.chdir(currDir)

#Remove the temporary user if he exists.
def unInitUser(user):
  username = user[:user.find('@')];
  if os.access('/Users/'+username+'/', os.F_OK)
    shutil.rmtree('/Users/'+username+'/')
    #subprocess.call(["sudo", "rm", "-rf", "/Users/"+username+"/"])
    subprocess.call(["sudo", "dscl",".","delete","/Users/"+username]);

#Good to know if the user needs to be removed.
def isUserStillActive(email, db):
  c = db.cursor();
  c.execute("SELECT * from devices WHERE email = '" + email + "';")
  if c.fetchone():
    c.close()
    return True
  c.close()
  return False

#Finds an available device to use.
#The devices are stored in a MySQL Database table 'devices'
def findUnusedDevice(deviceType, user, password, remote, ftp=None):
  #First, we need to check the LDAP server
  user, email = ldapQuery(user, password)
  #If user is not returned, then we have a bad login.
  if not user:
    return "Bad Username Or Password"
  #Setup DB Connection
  db = MySQLdb.connect(user="tegra",passwd="pool",db="TegraPool")
  activeUser = isUserStillActive(user, db)
  c = db.cursor()
  #Lock the table, as we don't want people checking them out simultaneously
  c.execute("LOCK TABLE devices WRITE;")
  c.execute("SELECT deviceIP, state FROM devices WHERE state = 'AVAILABLE' AND deviceType = '"+deviceType+"';")
  row = c.fetchone()
  if row:
    c.execute("UPDATE devices SET state = 'CHECKED_OUT', user = '" + user +
              "', email = '"+email+"' WHERE deviceIP = '" + row[0] + "';")
    c.execute("UNLOCK TABLES;")
    c.close()
    db.commit()
    setupDevice(row[0])
    print "Remote = " + str(remote)
    if remote and ftp and not activeUser:
      initUser(email, ftp, row[0]);
    return row[0]
  c.execute("UNLOCK TABLES;");
  c.close()
  db.commit()
  db.close()
  return None

#Finds the device in the device list and sets the user to None
#Returns true if the device was checked out previously.
def makeDeviceAvailable(ip):
  ipRegex = re.compile("(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})")
  ipMatch = ipRegex.search(ip)
  if ipMatch:
    ip = ipMatch.groups()[0]
  else:
    print "Not satisying Regex"
    return False;
  db = MySQLdb.connect(user="tegra",passwd="pool",db="TegraPool")
  c = db.cursor();
  c.execute("LOCK TABLE devices WRITE;")
  c.execute("SELECT state, email FROM devices WHERE deviceIP = '" + ip + "';")
  row = c.fetchone();
  #If device is not in list, or not checked out, return false.
  if not row or row[0] != 'CHECKED_OUT':
    c.execute("UNLOCK TABLES;");
    c.close();
    return False
  email = row[1]
  #Otherwise, update the device to be Rebooting
  c.execute("UPDATE devices SET state = 'REBOOTING', user = NULL, email = NULL WHERE deviceIP = '" + ip + "';")
  c.execute("UNLOCK TABLES;")
  db.commit()
  c.close()
  if not isUserStillActive(email, db):
    unInitUser(email)
  db.close()
  resetDevice(ip)
  return True

#Returns a list of device names and IPs that are checked out to that user.
def getUsedList(email):
  emailRegex = re.compile("(\S+@\S+\.\S+)")
  emailMatch = emailRegex.search(email)
  if emailMatch:
    email = emailMatch.groups()[0]
  else:
    return [];
  db = MySQLdb.connect(user="tegra",passwd="pool",db="TegraPool")
  c = db.cursor();
  c.execute("SELECT deviceid, deviceIP FROM devices WHERE email = '"
            + email + "';")
  result = c.fetchall()
  c.close()
  db.close()
  return result

#Quick method to return the majority of the device table.
def getTable(db):
  c = db.cursor();
  c.execute("SELECT deviceid, deviceIP, deviceType, state, user, email FROM devices;")
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
                                   postdata["password"],
                                   postdata["remote"],
                                   postdata["ftp"])
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
    db = MySQLdb.connect(user="tegra",passwd="pool",db="TegraPool")
    result = getTable(db)
    responseDict = {}
    for key in result:
      responseDict[key[0]] = (key[1],key[2],key[3],key[4], key[5])
    db.close()
    return responseDict 
    
#if __name__ == '__main__':
#  print "1"
#  initUser('btest@test.test')
#  print "2"
#  raw_input("Type Something Now! ")
#  print "3"
#  unInitUser('btest@test.test')
