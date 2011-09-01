import pickle

deviceFile = open("devices.txt", "w")
deviceList = {}
tegraIPs = ["000.000.000.000","111.111.111.111","222.222.222.222","255.255.255.255"]

for tegra in tegraIPs:
  deviceList[tegra] = (None,u"Tegra")

pickle.dump(deviceList, deviceFile);
