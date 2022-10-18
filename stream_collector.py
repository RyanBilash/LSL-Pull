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


After so many data entries per stream it'll print to file and clear stored data to not eat through memory
Eventually it might be changed to be based on time instead of raw sample count
"""

# How many samples should be stored before writing to file
COUNT_BREAK = 100
# How much leeway is accepted for timeout (means it will wait for the predicted wait time * acceptance)
TIMEOUT_ACCEPTANCE = 2.25

class stream_collector:
    def __init__(self, stream_name, keep_searching=True):
        self.stream_name = stream_name
        matching_streams = resolve_stream('name', stream_name)

        # Keep searching if it should
        while len(matching_streams) == 0 and keep_searching:
            matching_streams = resolve_stream('name', stream_name)
            time.sleep(1)

        # Make sure there is at least one stream found
        if len(matching_streams) > 0:
            self.inlet = StreamInlet(matching_streams[0])
            self.cached_stream_rate = self.stream_rate()
            self.cached_time_correction = self.time_correction()
            self.data = []
            self.running = True
            # Set the outfile to be based on the name of the stream and the start time for the data
            self.filename = self.stream_name + '_' + datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S") + '.csv'
        # self.resample_time_correction_rate = None # Unused method of regathering the time correction

    def collect(self, chunk_size=1):
        if self.cached_stream_rate != FOREVER:
            # Predict acceptable time for timeout
            timeout = (1/self.cached_stream_rate)*chunk_size*TIMEOUT_ACCEPTANCE
        else:
            timeout = FOREVER
        if chunk_size == 1:
            data, timestamp = self.inlet.pull_sample(timeout=timeout)
            if len(timestamp) < 1:
                # If it does timeout stop running and don't record the blank sample
                self.running = False
            else:
                self.data.append((timestamp - self.cached_time_correction, data))

            # Return as array for consistency
            return [data], [timestamp]
        elif chunk_size > 0:
            data, timestamps = self.inlet.pull_chunk(max_samples=chunk_size, timeout=timeout)
            for i in range(len(timestamps)):
                self.data.append((data[i], timestamps[i] - self.cached_time_correction))

            if len(timestamps) < chunk_size:
                # If it does timeout stop running
                self.running = False

            return data, timestamps

    def stream_rate(self):
        # Update the stream rate and cache it; it shouldn't change and isn't entirely necessary; primarily for logging
        self.cached_stream_rate = self.inlet.info().nominal_srate()
        return self.cached_stream_rate

    def time_correction(self):
        # Update time correction and cache it, returning the new value
        self.cached_time_correction = self.inlet.time_correction()
        return self.cached_time_correction

    def output_csv(self):
        filename = self.filename
        output_file = open(filename, 'a')
        output_writer = csv.writer(output_file)

        for i in self.data:
            # For some reason the file needs to be flushed at every row which it shouldn't need to
            output_writer.writerow(i)
            output_file.flush()
        output_file.close()
        self.data = []

        return filename


streams = []


def listening_thread(stream_name, keep_searching=False, chunk_size=1, log_data=False):
    # Make new stream, eventually collect data from it
    stream = stream_collector(stream_name, keep_searching)
    streams.append(stream)

    count = 0
    while stream.running:
        # Collect all data and every so many samples
        data, timestamps = stream.collect(chunk_size)
        if count >= COUNT_BREAK:
            stream.output_csv()
            count = 0
        else:
            count += len(timestamps)
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
            # Create new threads for each of the streams so they don't interfere with each other
            thread = threading.Thread(target=listening_thread, args=listener_args)
            thread.start()
            print(listener_args[0] + " thread started")

    file.close()


def exit_handler():
    # Just make sure to exit streams properly instead of just quitting the program
    for stream in streams:
        stream.running = False


if __name__ == "__main__":
    in_filename = input("Input filepath for file with stream names: ")
    atexit.register(exit_handler)
    read_file(in_filename)
