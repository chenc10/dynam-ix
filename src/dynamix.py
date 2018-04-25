#===================================================#
#                     Imports                       #
#===================================================#
import os
import sys
import threading
import subprocess
import socket
import json
from datetime import datetime
from datetime import timedelta
import hashlib
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto import Random
import base64
import time
import ipaddress
from Crypto.Cipher import ARC2
from Crypto.Hash import MD2
#===================================================#
#                   Global config                   #
#===================================================#
# AS config
myASN = sys.argv[1]
myAddress = sys.argv[2]
myIP = sys.argv[2].split(":")[0]
myPort = sys.argv[2].split(":")[1]
myService = sys.argv[3]
myPrivKey = ""
myPubKey = ""
myUser = sys.argv[5]
ordererIP = 'grpc://'+sys.argv[6]+':7050'

# Dictionaries contanining the offers that the AS have sent and received
offersSent = {}
offersRecvd = {}

# Dictionary containing the AS' interconnetion agreements
agreementsCust = {}
agreementsProv = {}

# Evaluation log
logs = open(myASN+".log", "w")

#===================================================#
#                     Functions                     #
#===================================================#
# Command line interface. Reads an instructions and call the appropriate function.
def cli():

    while True:
        action = raw_input("Dynam-IX: ")
        if len(action) > 0:
            if "registerAS" in action: # registerAS 'ASN' 'address' 'service' 'custRep' 'provRep' 'pubKey'
                x = subprocess.check_output('node js/register.js '+action+' '+myUser+' '+ordererIP, shell=True)
                print x
            elif "listASes" in action:  # listASes
                x = subprocess.check_output('node js/list.js'+' '+myUser, shell=True)
                print x
            elif "findService" in action: # findService service         # TODO fix this function when string has space
                #queryString = "{\"selector\":{\"service\":\"Transit\"}}"
                service = action.split("- ")[1]
                print service
                x = subprocess.check_output('node js/query.js findService \'{\"selector\":{\"service\":\"'+service+'\"}}\''+' '+myUser, shell=True)
                print x
            elif "show" in action: #show 'key'
                x = subprocess.check_output('node js/query.js '+action+' '+myUser, shell=True)
                print x
            elif "history" in action: #history 'key'
                x = subprocess.check_output('node js/query.js '+action+' '+myUser, shell=True)
                print x
            elif "delete" in action: #delete 'key'
                x = subprocess.check_output('node js/delete.js '+action+' '+myUser+' '+ordererIP, shell=True)
                print x
            elif "updateService" in action: #updateService 'ASN' 'newService'
                x = subprocess.check_output('node js/update.js '+action+' '+myUser+' '+ordererIP, shell=True)
                print x
            elif "updateAddress" in action: #updateAddress 'ASN' 'newAddress'
                x = subprocess.check_output('node js/update.js '+action+' '+myUser+' '+ordererIP, shell=True)
                print x
            elif "query" in action: #query providerASN request
                sendQuery(action)
            elif "propose" in action: #propose ID
                sendProposal(action)
            elif "listAgreements" in action:
                x = subprocess.check_output('node js/listAgreements.js'+' '+myUser, shell=True)
                print x
            elif "listOffersSent" in action:
                listOffersSent()
            elif "listOffersRecvd" in action:
                listOffersRecvd()
            elif "myAgreements" in action:
                myAgreements()
            elif "executeAgreements" in action:
                executeAgreements()
            elif "autonomous" in action:
                autonomous()
            elif "updateIntents" in action:
                intents = json.load(open(action.split(" ")[1]))
            elif "help" in action:
                help()
            elif "quit" in action:
                print "Quiting Dynam-IX"
                logs.close()
                os._exit(1)
            else:
                print "Invalid command. Type \'help\' to list the available commands.\n"

    return

def help():
    print("List of Dynam-IX commands")
    print("listASes - lists the ASes connected to the Dynam-IX blockchain")
    print("listAgreements - lists the interconnection agreements registered on Dynam-IX")
    print("query(ASx, TARGET, PROPERTIES) - sends a query to ASx for an interconnection agreement to reach prefix")
    print("\t\t example: query(AS2, 8.8.8.0/24, sla.latency == 15 && sla.bwidth >= 1000)")
    print("propose PROPOSAL_ID - sends an interconnection proposal request to the AS that offered the PROPOSAL_ID")
    print("\t\t example: propose AS2-AS1-123414121251")
    print("listOffersRecvd - lists the offeres that were received")
    print("listOffersSent - lists the offers that were sent")
    print("updateIntents PATH/TO/FILE - loads a new intent file")
    print("\t\t example: updateIntents newIntents.json")
    print("executeAgreements - updates the reputation of the ASes connected to me")
    print("myAgreements - lists my interconnection agreements")
    print("quit - quits Dynam-IX")

def autonomous():

    print "Entering autonomous mode!"
    time.sleep(90)  # Be sure to wait the necessary time to start

    AS = "AS1"
    num = int(sys.argv[8])
    sleepTime = int(sys.argv[9])

    print "Going to interact with "+AS+" doing "+str(num)+" queries/proposals every "+str(sleepTime)+" seconds"

    global offersRecvd

    total = 0
    while total < 30:
        offersRecvd = {}

        for i in range(0,num):
            #query AS prefix
            query = "query "+AS+" 8.8.8.0/24"
            sendQuery(query)

        while len(offersRecvd) < num:
            #print "Number of offers: "+str(len(offersRecvd))
            time.sleep(0.5)

        for offer in offersRecvd.keys():
            offerID = offer

            proposal = "propose "+offerID
            #propose offerID
            sendProposal(proposal)

        total = total + num
        #print "Sleeping"
        #time.sleep(1)
        #print "Waking up"

    print "Leaving autonomous mode!"
    time.sleep(300)  # Be sure of getting all agreements answers
    print "Quiting Dynam-IX"
    logs.close()
    os._exit(1)

# Receive messages and create threads to process them
def processMessages():

    messageThreads = []

    # Open socket to accept connections
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind((myIP, int(myPort)))
    serversocket.listen(256) # NOTE We may need to increase the number simultaneous requests

    while True:
        connection, address = serversocket.accept()
        msg = ''
        msg = connection.recv(4096)     # NOTE We may need to change the amount of received bytes

        try:
            encryptMsg = msg.split('signatures')[0]
        except ValueError:
            encryptMsg = msg
        try:
            signatures = msg.split('signatures')[1]
        except IndexError:
            signatures = ''

        msg = myPrivKey.decrypt(encryptMsg) + signatures

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        if len(msg) > 0:
            if "query" in msg:  # Customer is asking for an offer
                # logging
#                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logs.write(timestamp+";RQ;"+msg.split(";")[3]+"\n")
                t = threading.Thread(target=sendOffer, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "offer" in msg: # Provider have sent an offer
                # logging
#                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logs.write(timestamp+";RO;"+msg.split(";")[3]+"\n")
                t = threading.Thread(target=collectOffer, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "propose" in msg: # Customer is asking to establish an interconnection agreement
                # logging
#                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logs.write(timestamp+";RP;"+msg.split(";")[1]+"\n")
                t = threading.Thread(target=establishAgreement, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "contract" in msg: # Provider have sent the contract to be signed
                # logging
#                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logs.write(timestamp+";RC;"+msg.split(";")[1]+"\n")
                t = threading.Thread(target=signContract, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "publish" in msg:  # Customer is sending the signed contract to be registered on the ledger
                # logging
#                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logs.write(timestamp+";RS;"+msg.split(";")[1]+"\n")
                t = threading.Thread(target=publishAgreement, args=(msg,))
                messageThreads.append(t)
                t.start()
            elif "ack" in msg:  # Customer is sending the signed contract to be registered on the ledger
                print "Success! Updating routing configuration!"
                # logging
#                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                logs.write(timestamp+";RU;"+msg.split(";")[1]+"\n")
                t = threading.Thread(target=verifyUpdate, args=(msg,))
                messageThreads.append(t)
                t.start()
            else:
                print "Invalid message\n"

def verifyUpdate(ack):

    offerID = ack.split(";")[1]
    IA = ack.split(";")[2]

    out = ""

    while "hash" not in out:
        out = subprocess.check_output('node js/query.js show '+IA+' '+myUser, shell=True)
        time.sleep(1)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    logs.write(timestamp+";VU;"+offerID+"\n")

def sendMessage(msg, ip, port, pubKey, flag):

    # Encrypt message with the pubKey
    # contract MSG
    if flag == 1:
        signature = msg.split(';')[5]
        msg = msg.split(';')[0]+';'+msg.split(';')[1]+';'+msg.split(';')[2]+';'+msg.split(';')[3]+';'+msg.split(';')[4]+';'
        encryptMSG = pubKey.encrypt(msg, 0)[0]+'signatures'+signature
    # publish MSG
    elif flag == 2 :
        signature1 = msg.split(';')[5]
        signature2 = msg.split(';')[6]
        msg = msg.split(';')[0]+';'+msg.split(';')[1]+';'+msg.split(';')[2]+';'+msg.split(';')[3]+';'+msg.split(';')[4]+';'
        encryptMSG = pubKey.encrypt(msg, 0)[0]+'signatures'+signature1+';'+signature2
    else:
        encryptMSG = pubKey.encrypt(msg, 0)[0]

    clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientsocket.connect((ip, port))
    clientsocket.send(encryptMSG)
    clientsocket.close()

# Receives a query action and send it to a potential provider
def sendQuery(action):

    n = len(action.split(","))

    # query(AS2, 8.8.8.0/24, sla.latency == 10 && sla.repair < 0.5)
    # Get provider's ASN
    provider = action.split(",")[0]
    provider = provider[6:]

    # Query the ledger to get the provider's address
    address = ""
    while ":" not in address:
        address = getAddress(provider)

    # Split the address into IP and port
    IP = address.split(":")[0]
    port = int(address.split(":")[1])

    # Get the query
    if n == 3:
        properties = action.split(",")[2]
        properties = properties[1:-1]
        intent = action.split(",")[1]
        intent = intent[1:]
        query = intent + " " + properties
    else:
        #properties = "null"
        intent = action.split(",")[1]
        intent = intent[1:-1]
        query = intent

    # Query the ledger to get the provider's public key
    pubkey = getPubKey(provider)

    # Evaluation control
    # Generate the query/offer ID
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    ID = myASN+"-"+provider+"-"+timestamp

    # Create the message that is going to be sent
    msg = 'query;'+myASN+';'+query+";"+ID # TODO encrypt with provider's pubkey

    # logging
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    # Send the query to the provider
    sendMessage(msg, IP, port, pubkey, 0)

    # logging
    logs.write(timestamp+";SQ;"+ID+"\n")


# get AS' reputation as a customer or as a provider from the ledger
def getReputation(ASN, role):

    x=""

    while "address" not in x:
        # Query the ledger to get AS' information
        x = subprocess.check_output('node js/query.js show \''+ASN+'\''+' '+myUser, shell=True)
    # Get the reputation
    if role == "customer":
        return x.split(",")[1].split(':')[1]
    elif role == "provider":
        return x.split(",")[2].split(':')[1]

# get AS' address from the ledger
def getAddress(ASN):

    x=""

    while "address" not in x:
        # Query the ledger to get AS' information
        x = subprocess.check_output('node js/query.js show \''+ASN+'\''+' '+myUser, shell=True)
    # Get the address
    aux = x.split(",")[0]
    ip = aux.split(":")[1]
    port = aux.split(":")[2]

    # Return ip:port
    return ip.split("\"")[1]+":"+port.split("\"")[0]

# get AS' public key from the ledger
def getPubKey(ASN):

    x=""

    while "address" not in x:
        # Query the ledger to get AS' information
        x = subprocess.check_output('node js/query.js show \''+ASN+'\''+' '+myUser, shell=True)
    S = x.split(",")[3].split(":")[1]

    #transform pubKey String in a pubKey obj
    pubKeyString = S.split("\"")[1]
    pubKeyString = pubKeyString.replace('\\n','\n')
    pubKey = RSA.importKey(pubKeyString)

    return pubKey

# Receive a query from a customer, decide if it is going to answer, and compose and agreement offer
def sendOffer(query):
    # queryFormat = query;customerASN;properties
    print "Received : "+query

    # Get customer's ASN
    customer = query.split(";")[1]
    # Verify customer's reputation
    reputation = 1 #getReputation(customer, "customer")
    # If AS is a good customer, send offer
    if int(reputation) >= 0:                # TODO Define reputation threshold
        # Check interconnection policy to compose and offer to the customer
        ID = query.split(";")[3]
        offer = composeOffer(query.split(";")[2], customer, ID)
        # If provider can offer something, send
        if offer != -1:
            # Get customer's address
            address = ""
            while ":" not in address:
                address = getAddress(customer)
            #print "Got address "+address+" for query "+query
            # Split address into IP and port
            IP = address.split(':')[0]
            port = int(address.split(':')[1])
            # Get customer's public key
            pubKey = getPubKey(customer)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            #Send offer
            sendMessage(offer+";"+ID, IP, port, pubKey, 0)

            # logging
            logs.write(timestamp+";SO;"+ID+"\n")

        # Provider is not able to offer an agreement with the desired properties
        else:
           print "I cannot offer an agreement!"
    # Customer has poor reputation
    else:
        print "Customer with poor reputation!"

# Check the interconnection policy and compose and offer to be sent to the customer
def composeOffer(query, customer, ID):

    # Generate the offer ID
#    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
#    ID = myASN+"-"+customer+"-"+timestamp

#    offer = "offer;"+ID+";"+query+";10$;"+expireDate
    properties = checkIntents(query)

    if properties != -1:
        # Store the offer on the list. This is important to verify if the offer is still valid when the customer sends the proposal message.
        storeOffer(ID+";"+properties, "sent")
        #return offer
        return "offer;"+ID+";"+properties
    else:
        return properties

def checkIntents(query):

    i = 0

    n = len(query.split(" "))
    customerIntent = query.split(" ")[0]

    if n > 1:
        customerProperties = query[len(customerIntent)+1:]
    else:
        customerProperties = "null"

    customerAddress,subnetCustomer = customerIntent.split("/")

    #turns a string into ipv4address
    customerAddress = ipaddress.ip_address(unicode(customerAddress))

    # iterate over provider's intents
    while i < len(intents.keys()):
        fileIntent = str(intents.keys()[i])
        fileAddress,subnetIntent = fileIntent.split("/")

        #turns a string into ipv4network
        fileIntent = ipaddress.ip_network(unicode(fileIntent))

        if subnetCustomer >= subnetIntent:
            if customerAddress in fileIntent:
                if checkproperties(customerProperties,i) == 1:
                    offer = fillOffer(i)
                    return offer

        i = i + 1

    # return -1 if the provider cannot offer an agreement with the desired propertiess
    return -1

def checkproperties(customerProperties,i):

    k = 0

    if customerProperties == "null":
        return 1
    else:
        try:
            properties = customerProperties.split("&& ")
        except ValueError:
            properties = customerProperties

        # iterate over customer's properties
        while k < len(properties):

            testProp = properties[k]

            #TODO assuming the same command line as shown in help: query(AS2, 8.8.8.0/24, sla.latency == 10 && sla.repair < 0.5)
            prop = testProp.split(" ")[0]
            value = testProp.split(" ")[2]

            if prop == "sla.bwidth" and float(value) > float(intents[intents.keys()[i]]["sla"]["bandwidth"]):
                return -1
            elif prop == "sla.latency" and float(value) < float(intents[intents.keys()[i]]["sla"]["latency"]):
                return -1
            elif prop == "sla.pkt_loss" and float(value) < float(intents[intents.keys()[i]]["sla"]["loss"]):
                return -1
            elif prop == "sla.jitter" and float(value) < float(intents[intents.keys()[i]]["sla"]["jitter"]):
                return -1
            elif prop == "sla.repair" and float(value) < float(intents[intents.keys()[i]]["sla"]["repair"]):
                return -1
            elif prop == "sla.guarantee" and float(value) > float(intents[intents.keys()[i]]["sla"]["guarantee"]):
                return -1
            elif testProp == "sla.availability" and float(value) > float(intents[intents.keys()[i]]["sla"]["availability"]):
                return -1
            elif prop == "pricing.egress" and float(value) < float(intents[intents.keys()[i]]["pricing"]["egress"]):
                return -1
            elif prop == "pricing.ingress" and float(value) < float(intents[intents.keys()[i]]["pricing"]["ingress"]):
                return -1
            elif prop == "pricing.billing" and str(value) != str(intents[intents.keys()[i]]["pricing"]["billing"]):
                return -1
            elif prop != "sla.bwidth" and prop != "sla.latency" and prop != "sla.pkt_loss" and prop != "sla.jitter" and prop != "sla.repair" and prop != "sla.guarantee" and prop != "sla.availability" and prop != "pricing.egress" and prop != "pricing.ingress" and prop != "pricing.billing":
                print "Invalid Propertie: ", prop
                return -1
            else:
                k = k+1

        return 1

def fillOffer(i):

    target = "target:"+str(intents.keys()[i])
    aspath = ",routing.aspath:"+str(intents[intents.keys()[i]]["routing"]["aspath"])
    bandwidth = ",sla.bandwidth:"+str(intents[intents.keys()[i]]["sla"]["bandwidth"])
    latency = ",sla.latency:"+str(intents[intents.keys()[i]]["sla"]["latency"])
    jitter = ",sla.jitter:"+str(intents[intents.keys()[i]]["sla"]["jitter"])
    loss = ",sla.loss:"+str(intents[intents.keys()[i]]["sla"]["loss"])
    repair = ",sla.repair:"+str(intents[intents.keys()[i]]["sla"]["repair"])
    availability = ",sla.availability:"+str(intents[intents.keys()[i]]["sla"]["availability"])
    guarantee = ",sla.guarantee:"+str(intents[intents.keys()[i]]["sla"]["guarantee"])
    egress = ",pricing.egress:"+str(intents[intents.keys()[i]]["pricing"]["egress"])
    ingress = ",pricing.ingress:"+str(intents[intents.keys()[i]]["pricing"]["ingress"])
    billing = ",pricing.billing:"+str(intents[intents.keys()[i]]["pricing"]["billing"])
    length = ",time.length:"+str(intents[intents.keys()[i]]["time"]["unit"])
    expireDate = ",time.expire:"+str(datetime.now() + timedelta(hours=6))

    offer = target+aspath+bandwidth+latency+jitter+loss+repair+availability+guarantee+egress+ingress+billing+length+expireDate

    return offer

# Receive an offer and store it on the appropriate dictionary
def collectOffer(offer):

    ID = offer.split(";")[1]
    properties = offer.split(";")[2]

    print "Received: "+ offer
    storeOffer(ID+";"+properties, "recvd")

# Store an offer on the appropriate dictionary
def storeOffer(offer, direction):

    ID = offer.split(";")[0]
    properties = offer.split(";")[1]

    if direction == "sent":
        offersSent[ID] = properties
    elif direction == "recvd":
        offersRecvd[ID] = properties

# Print all the offers that were sent to customers
def listOffersSent():

    for offer in offersSent:
        print offer, offersSent[offer]

# Print all the offers that were received from providers
def listOffersRecvd():

    for offer in offersRecvd:
        print offer, offersRecvd[offer]

# Delete expired offers
def cleanOffers():

    #if offer expired, remove
    return

# Send an interconnection proposal to an AS
def sendProposal(action):
    # action = propose offerID

    # Get only the offerID
    offerID = action.split("propose ")[1]
    # Get the provider's ASN
    provider = offerID.split("-")[1]
    pubKey = getPubKey(provider)
    # If the offer is still valid, send interconnection proposal to the provider
    if checkValidity(offerID) == 1:
        # Get provider's address
        address = ""
        while ":" not in address:
            address = getAddress(provider)        # Split address into IP and port
        IP = address.split(':')[0]
        port = int(address.split(':')[1])
        # Send interconnection proposal
        msg = "propose"+";"+offerID
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        sendMessage(msg, IP, port, pubKey, 0)

        # logging
        logs.write(timestamp+";SP;"+offerID+"\n")

    # If the offer is not valid anymore, there is no reason to send the interconnection proposal
    else:
        print "Offer is not valid anymore!"

# Check if the offer is not expired
def checkValidity(offerID):

    # query offersSent[offerID]
    # get expireDate

    # if time.now() < expireDate:
    #    return 1
    # else:
    #   return -1

    return 1

# Receive a propose message and send the contract if the offer is still valid
def establishAgreement(propose):

    offerID = propose.split(";")[1]
    pubKey = getPubKey(propose.split("-")[1])

    print "Received: "+propose

    # If offer is still valid, send the contract
    if checkValidity(offerID) == 1:
        sendContract(offerID)
    # Offer is no longer valid
    else:
        msg = "Offer is no longer valid"
        print msg
        # TODO get address
        # Send message
        sendMessage(msg, IP, port, pubKey, 0)


# Send the contract of the interconnection agreement to the customer
def sendContract(offerID):

    # Get customer's ASN
    customer = offerID.split("-")[0]
    provider = myASN

    # Get customer's pubKey
    pubKey = getPubKey(customer)

    # Get provider's address
    address = ""
    while ":" not in address:
        address = getAddress(customer)
    # Split address into IP and port
    IP = address.split(':')[0]
    port = int(address.split(':')[1])

    # Write the contract
    contract = "contract of the Interconnection agreement between "+provider+" and "+customer+offerID

    # Compute the contract hash
    hash_object = hashlib.md5(contract.encode())
    h = hash_object.hexdigest()

    # Provider signs the contract
    providerSignature = myPrivKey.sign(h,0)

    # Send the contract
    msg = "contract;"+offerID+";"+h+";"+customer+";"+provider+";"+str(providerSignature[0])

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    sendMessage(msg, IP, port, pubKey, 1)

    # logging
    logs.write(timestamp+";SC;"+offerID+"\n")

# Customer sign the contract
def signContract(contract):

    # Remove message header
    s = contract.split("contract;")[1]
    # Get the contract hash
    h = contract.split(";")[2]

    # Get provider's ASN
    provider = contract.split(";")[4]

    # Get the contract hash
    providerSignature = contract.split(";")[5]

    # Get provider's pubKey
    pubKey = getPubKey(provider)

    # Customer verify the provider signature
    if pubKey.verify(h, (long(providerSignature),0)) == False:
        print "Invalid signature!"
    else:
        # Customer signs the contract
        customerSignature = myPrivKey.sign(h,0)

        # Get provider's address
        address = ""
        while ":" not in address:
            address = getAddress(provider)    # Split address into IP and port
        IP = address.split(':')[0]
        port = int(address.split(':')[1])

        # Send message with the contract signed by the customer
        msg = "publish;"+s+";"+str(customerSignature[0])
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        sendMessage(msg, IP, port, pubKey,2)

        # logging
        logs.write(timestamp+";SS;"+contract.split(";")[1]+"\n")

        key = "IA-"+h
        agreementsCust[key] = myASN+";"+provider

def publishAgreement(info):

    # Get the parameters that will be registered on the ledger
    contractHash = info.split(";")[2]
    customer = info.split(";")[3]
    provider = myASN
    providerSignature = info.split(";")[5]
    customerSignature = info.split(";")[6]

    # Get customer's pubKey
    pubKey = getPubKey(customer)

    # Provider verify the customer signature
    if pubKey.verify(contractHash, (long(customerSignature),0)) == False:
        print "Invalid signature!"
    else:

        key = "IA-"+contractHash

        # Register the agreement on the ledger
        x = subprocess.check_output('node js/publish.js registerAgreement \''+key+'\' \''+contractHash+'\' \''+customer+'\' \''+provider+'\' \''+customerSignature+'\' \''+providerSignature+'\''+' '+myUser+' '+ordererIP, shell=True)
        agreementsProv[key] = customer+";"+provider
        print key+" Success! Updating routing configuration!"

        # Get customer's address
        address = ""
        while ":" not in address:
            address = getAddress(customer)
        # Split address into IP and port
        IP = address.split(':')[0]
        port = int(address.split(':')[1])

        offerID=info.split(";")[1]

        # Send message with the key
        msg = "ack;"+offerID+";"+key
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        sendMessage(msg, IP, port, pubKey, 0)

        # logging
        logs.write(timestamp+";SU;"+offerID+"\n")

def executeAgreements():

    for agmnt in agreementsProv.keys():
        #if ended
        customer = agreementsProv[agmnt].split(";")[0]
        print customer
        # update customer's reputation
        x = subprocess.check_output('node js/update.js updateCustRep \''+customer+'\' \'1\''+' '+myUser+' '+ordererIP, shell=True)
        print x

        del agreementsProv[agmnt]

    for agmnt in agreementsCust.keys():
        #if ended
        provider = agreementsCust[agmnt].split(";")[1]
        print provider
        # update provider's reputation
        x = subprocess.check_output('node js/update.js updateProvRep \''+provider+'\' \'1\''+' '+myUser+' '+ordererIP, shell=True)
        print x

        del agreementsCust[agmnt]

    return

def myAgreements():

    for agmnt in agreementsCust:
        print agmnt, agreementsCust[agmnt]
    for agmnt in agreementsProv:
        print agmnt, agreementsProv[agmnt]

def end():

    time.sleep(1200)
    print "Quiting Dynam-IX"
    logs.close()
    os._exit(1)

#Main function
if __name__ == "__main__":

    # Generate public and private keys
    basePhrase = myASN+myASN+"Dynam-IX"
    baseNumber = Random.new().read
    myPrivKey = RSA.generate(4096, baseNumber)
    myPubKey = myPrivKey.publickey()
    myPubKeyString = myPubKey.exportKey('PEM')

    # Read intent file
    intents = json.load(open(sys.argv[4]))

    # TODO optimize to not query the blockchain
    # If AS is not registered
    if '{' not in subprocess.check_output('node js/query.js show \''+myASN+'\''+' '+myUser, shell=True):
        print "Registering new AS", myASN, myAddress, myService
        x = subprocess.check_output('node js/register.js registerAS \''+myASN+'\' \''+myAddress+'\' \''+myService+'\' \'0\' \'0\' \''+myPubKeyString+'\''+' '+myUser+' '+ordererIP, shell=True)
        print x
    # else, update address
    else:
        print "Updating AS address", myASN, myAddress, myService
        x = subprocess.check_output('node js/update.js updateAddress \''+myASN+'\' \''+myAddress+'\''+' '+myUser+' '+ordererIP, shell=True)

    mode = sys.argv[7]

    # Start threads
    threads = []
    if mode == "autonomous":
        t = threading.Thread(target=autonomous)
        threads.append(t)
        t.start()
        #t = threading.Thread(target=end)
        #threads.append(t)
        #t.start()
    else:
        t = threading.Thread(target=cli)
        threads.append(t)
        t.start()
    t = threading.Thread(target=processMessages)
    threads.append(t)
    t.start()
