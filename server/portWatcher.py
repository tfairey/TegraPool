import socket
import urlparse
import MySQLdb

#Set up the port to be listened on. 
HOST = ''
PORT = 28001
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((HOST,PORT))

#Set up db for database connection


#Permanent loop listening to the port waiting for a ping. 
while 1:
  s.listen(1)
  conn, addr = s.accept()
  print 'Connected by', addr
  data = conn.recv(1024)
  #print("Data= " +data)
  data = data.lstrip("register ")
  info = urlparse.parse_qs(data)
  #print info
  print "NAME = " + info['NAME'][0]
  print "IP = " + info['IPADDR'][0]
  #When a ping arrives, store the information in the devices table.
  #NOTE: Issue occurs if the PINGs arrive faster than
  #data can be written to the database.
  inputted = False
  while not inputted:
    try:
      db = MySQLdb.connect(user="tegra",db="TegraPool")
      c=db.cursor();
      c.execute("LOCK TABLE devices WRITE");
      c.execute("INSERT INTO devices (deviceid,deviceIP,state) VALUES ('"+
                 info['NAME'][0]+"','" + info['IPADDR'][0] +
                 "','AVAILABLE') ON DUPLICATE KEY UPDATE state='AVAILABLE';")
      c.execute("UPDATE devices SET state='CHECKED_OUT' WHERE deviceIP ='" +
                info['IPADDR'][0] + "' AND user IS NOT NULL;")
      c.execute("UNLOCK TABLES;")
      db.commit()
      c.close()
      db.close()
      conn.close()
      inputted = True
    except:
      if c:
        c.close()
      if db: 
        db.close()
      

