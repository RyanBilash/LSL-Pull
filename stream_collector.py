import csv
from pylsl import *
import time
import datetime
import threading
import atexit


"""
File format (each line) should be '<streamname>;<keep_searching>'
where keep_searching is true or false
and has optional inputs of ';<chunk_size>;<log_data>'
where chunk_size is an int greater than 0 and log_data is another true or false

Right now the way to write to file is on exiting the program or setting all streams to not running
This will be changed soon to allow for partial writes to deal with memory
"""

class stream_collector:
    def __init__(self, stream_name, keep_searching=False):
        self.stream_name = stream_name
        matching_streams = resolve_stream('name', stream_name)

        while len(matching_streams) == 0 and keep_searching:
            matching_streams = resolve_stream('name', stream_name)
            time.sleep(1)

        self.inlet = StreamInlet(matching_streams[0])
        self.cached_stream_rate = self.stream_rate()
        self.cached_time_correction = self.time_correction()
        self.data = []
        self.running = True
        # self.resample_time_correction_rate = None # Unused method of regathering the time correction

    def collect(self, chunk_size=1):
        if chunk_size == 1:
            data, timestamp = self.inlet.pull_sample()
            self.data.append((timestamp - self.cached_time_correction, data))
            return [data], [timestamp]
        elif chunk_size > 0:
            data, timestamps = self.inlet.pull_chunk(max_samples=chunk_size)
            for i in range(len(timestamps)):
                self.data.append((data[i], timestamps[i] - self.cached_time_correction))
            return data, timestamps

    def stream_rate(self):
        self.cached_stream_rate = self.inlet.info().nominal_srate()
        return self.cached_stream_rate

    def time_correction(self):
        self.cached_time_correction = self.inlet.time_correction()
        return self.cached_time_correction

    def get_filename(self):
        return self.stream_name + '_' + datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S") + '.csv'

    def output_csv(self):
        filename = self.get_filename()
        output_file = open(self.stream_name + ".csv", 'w')
        output_writer = csv.writer(output_file)

        for i in self.data:
            output_writer.writerow(i)
            output_file.flush()
        output_file.close()

        return filename


streams = []


def listening_thread(stream_name, keep_searching=False, chunk_size=1, log_data=False):
    stream = stream_collector(stream_name, keep_searching)
    streams.append(stream)

    while stream.running:
        data, timestamps = stream.collect(chunk_size)
        if log_data:
            print(data, timestamps)
    stream.output_csv()


def read_file(filename):
    file = open(filename, 'r')
    lines = file.readlines()
    for line in lines:
        listener_args = None
        try:
            # Split at ; for the name,  and other optional settings
            split_line = line.split(";")
            split_line[1] = split_line[1].replace(" ", "")
            listener_args = [split_line[0], split_line[1].lower().startswith('t')]

            # Get chunk size
            if len(split_line) > 2:
                split_line[2] = split_line[2].replace(" ", "")
                listener_args.append(int(split_line[2]))

            # Get whether or not data should be logged to console
            if len(split_line) > 3:
                split_line[3] = split_line[3].replace(" ", "")
                listener_args.append(split_line[3].lower().startswith('t'))
        except:
            print('Error with line "' + line + '"')
            continue

        if listener_args is not None:
            thread = threading.Thread(target=listening_thread, args=listener_args)
            thread.start()
            print(listener_args[0] + " thread started")

    file.close()


def exit_handler():
    for stream in streams:
        stream.running = False


if __name__ == "__main__":
    in_filename = input("Input filepath for file with stream names: ")
    atexit.register(exit_handler)
