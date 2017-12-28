import sys
import os
import socket
import threading
import subprocess

#AS config
myASN = sys.argv[1]
myAddress = sys.argv[2]
myIP = sys.argv[2].split(":")[0]
myPort = sys.argv[2].split(":")[1]
myPubKey = sys.argv[3]
myService = sys.argv[4]

def cli():

    while True:
        action = raw_input("Dynam-IX: ")
        if len(action) > 0:
            if "register" in action: #Register 'ASN' 'address' 'service' 'custRep' 'provRep' 'pubKey'
                x = subprocess.check_output('node register.js '+action, shell=True)
                print x
            elif "list" in action:  #list 
                x = subprocess.check_output('node list.js', shell=True)
                print x
            elif "findService" in action: #findService service
                #queryString = "{\"selector\":{\"service\":\"Transit\"}}"
                service = action.split("-")[1]
                print service
                x = subprocess.check_output('node query.js findService \'{\"selector\":{\"service\":\"'+service+'\"}}\'', shell=True)
                print x
            elif "findAS" in action: #findAS 'ASN'
                x = subprocess.check_output('node query.js '+action, shell=True)
                print x
            elif "history" in action: #history 'ASN'
                x = subprocess.check_output('node query.js '+action, shell=True)
                print x
            elif "delete" in action: #delete 'ASN'
                x = subprocess.check_output('node delete.js '+action, shell=True)
                print x
            elif "updateService" in action: #updateService 'ASN' 'newService'
                x = subprocess.check_output('node update.js '+action, shell=True)
                print x
            elif "updateAddress" in action: #updateAddress 'ASN' 'newAddress'
                x = subprocess.check_output('node update.js '+action, shell=True)
                print x
            elif "query" in action: #query providerASN request
                sendQuery(action)
            elif "establish" in action: #establish
                establishAgreement(action)
            elif "quit" or "exit" in action:
                 os._exit(1)
            else:
                print "Invalid command\n"

    return

def sendQuery(action):

    ASN = action.split(" ")[1]
    S = getAddress(ASN)
    address = S.split(":")[0]
    port = int(S.split(":")[1])
    query = action.split(" ")[2]
    clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientsocket.connect((address, port))
    pubkey = getPubKey(ASN)
    msg = 'query;'+myASN+';'+query #encrypt with provider's pubkey
    clientsocket.send(msg)
    clientsocket.close()

def getReputation(ASN, role):

    x = subprocess.check_output('node query.js findAS \''+ASN+'\'', shell=True)
    if role == "customer":
        return x.split(",")[1].split(':')[1]
    elif role == "provider":
        return x.split(",")[2].split(':')[1]

def getAddress(ASN):

    x = subprocess.check_output('node query.js findAS \''+ASN+'\'', shell=True)
    S = x.split(",")[0]
    addr = S.split(":")[1]
    port = S.split(":")[2]

    return addr.split("\"")[1]+":"+port.split("\"")[0]

def getPubKey(ASN):

    x = subprocess.check_output('node query.js findAS \''+ASN+'\'', shell=True)
    S = x.split(",")[3].split(":")[1]

    return S.split("\"")[1]

def sendOffer(query):

    print "\nI will check if I can send an offer\n"
    print query
    ASN = query.split(";")[1]
    reputation = getReputation(ASN, "customer")
    if int(reputation) >= 0:
        addr = getAddress(ASN)
        address = addr.split(':')[0]
        port = int(addr.split(':')[1])
        #composeOffer(query.split(";")[2])
        offer = 'offer;10' # + ASN + pubkey
        #if len(offer) > 0:
        clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        clientsocket.connect((address, port))    
        clientsocket.send(offer)
        clientsocket.close()    
    else:
        print "Bad reputation!"

    return 

def collectOffer(offer):
    
    print "\nCollecting offer\n"
    print "Received: "+ offer
#    storeOffer(m)
    return

def establishAgreement():

    print "\nI will check if the proposal is still valid\n"
 #     if checkValidity(m):
 #           createSmartContract()
 #           publishSmartContract()
 #           updateNetworkConfiguration()
 #    else:
 #           sendMessage("This offer is not valid anymore!")
    return

def processMessages():

    messageThreads = []

    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    serversocket.bind((myIP, int(myPort)))
    serversocket.listen(20) #maximum of 20 simultaneous requests 

    while True:
        connection, address = serversocket.accept()
        msg = ''
        msg = connection.recv(1024)
        if len(msg) > 0:
            if "query" in msg:
                t = threading.Thread(target=sendOffer, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "offer" in msg:
                t = threading.Thread(target=collectOffer, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "proposal" in msg:
                t = threading.Thread(target=establishAgreement, args=(msg,))
                messageThreads.append(t)
                t.start()
            else:
                print "Invalid message\n"

    return

#Main function
if __name__ == "__main__":

    #optimize to not query the blockchain
    #If AS is not registered
    if '{' not in subprocess.check_output('node query.js findAS \''+myASN+'\'', shell=True):
        x = subprocess.check_output('node register.js register \''+myASN+'\' \''+myAddress+'\' \''+myService+'\' \'0\' \'0\' \''+myPubKey+'\'', shell=True)
        print x
    #else, update address
    else:
        x = subprocess.check_output('node update.js updateAddress \''+myASN+'\' \''+myAddress+'\'', shell=True)

    threads = []
    t = threading.Thread(target=cli)
    threads.append(t)
    t.start()
    t = threading.Thread(target=processMessages)
    threads.append(t)
    t.start()