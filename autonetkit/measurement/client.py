"""Zmq based measurement client"""
import zmq
import sys
import random
import time
import json
import autonetkit
import pkg_resources
import os
import autonetkit.measurement.process as process

server = "54.252.204.52"
port = "5559"

#print "Connecting to server..."
#socket = context.socket(zmq.REQ)
#socket.connect ("tcp://54.252.148.199:%s" % port)
#socket = context.socket(zmq.REQ)
#socket.connect ("tcp://localhost:%s" % port)

def main():
    import Queue
    from threading import Thread

    nidb = autonetkit.NIDB()
    nidb.restore_latest()
    rev_map = process.build_reverse_mappings_from_nidb(nidb)

    template_file = pkg_resources.resource_filename(__name__, "../textfsm/linux/traceroute")
    template_file = os.path.abspath(template_file)

    commands = []
    import random
    dest_node = random.choice([n for n in nidb.nodes("is_l3device")])
    dest_ip = list(dest_node.physical_interfaces)[0].ipv4_address
    cmd = "traceroute -n -a -U -w 0.5 %s" % dest_ip
    #cmd = "traceroute -n -a -U -w 0.5 10.5.0.2"

    for node in nidb.routers():
        commands.append({'host': str(node.tap.ip),
         'username': "root", "password": "1234",
         "command": cmd, "template": template_file, "rev_map" : rev_map,
         "source": node,
          })

    def do_work(socket, data):
        #TODO: make username and password optional
        message = json.dumps(data)
        socket.send (message)
        print "waiting for response for %s" % message
        message = socket.recv()
        data = json.loads(message)
        print data
        return str(data)

    def process_data(user_data, result):
        # TODO: test if command is traceroute
        template = user_data['template']
        rev_map = user_data['rev_map']
        source = user_data['source']
        header, routes = process.process_traceroute(template_file, result)
        path = process.extract_path_from_parsed_traceroute(header, routes)
        hosts = process.reverse_map_path(rev_map, path)
        hosts.insert(0, source)
        #TODO: push processing results onto return values
        import autonetkit.ank_messaging as ank_messaging
        path_data = {'path': hosts}
        print hosts
        ank_messaging.highlight(paths = [path_data])

    results_queue = Queue.Queue()

    #TODO: check why can't ctrl+c
    def worker():
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect ("tcp://%s:%s" % (server, port))
        while True:
            try:
                (_, key, item)  = q.get(timeout=1)
            except Queue.Empty:
                return
            if key == "command":
                # only send the core information: not extra info for parsing
                core_keys = ("host", "username", "password", "command")
                core_data = {k: v for k,v in item.items() if k in core_keys}
                result = do_work(socket, core_data)
                q.put((10, "process", (item, result)))
            if key == "process":
                user_data, result = item
                process_data(user_data, result)

            q.task_done()

    q = Queue.PriorityQueue()
    num_worker_threads = 3
    for i in range(num_worker_threads):
        t = Thread(target=worker)
        t.daemon = True
        t.start()

    for item in commands:
        q.put((20, "command", item))

    q.join()

    print "Finished measurement"

    # now read off results queue
    output_results = []
    while True:
        try:
            item = results_queue.get(timeout=1)
        except Queue.Empty:
            break
        output_results.append(item)


if __name__ == "__main__":
    main()