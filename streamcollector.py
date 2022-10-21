import csv
from pylsl import *
import time
import datetime
import threading
import atexit

"""
File format (each line) should be '<streamname>;<keep_searching>'
where keep_searching is true or false
and has optional inputs of ';<chunk_size>;<log_data>;<outfile>'
where chunk_size is an int greater than 0 and log_data is another true or false
and outfile can have .csv but it isn't necessary

After so many data entries or time between writes, it'll write all data to file and clear data for the sake of memory

Each stream outputs to a different file because actually aligning the data isn't the easiest but might change later
"""

# How many samples should be stored before writing to file
COUNT_BREAK = 100
# How long to wait time-wise between writing to files
TIME_BREAK = 1000  # 1 second
# Choose whether to write to file after certain time (f) or sample count (t)
WRITE_WITH_COUNT = True
# How much leeway is accepted for timeout (means it will wait for the predicted wait time * acceptance)
TIMEOUT_ACCEPTANCE = 2.25

# Active streams for simple collection purpose
streams = []

# Idea: output_files(outfilename) = {timestamp : {channel : data}}} (timestamps are more approximate but still
# should work) triple dict for all this - maybe generate timestamps based on the first data entry and the most
# frequent sample rate of the streams that will be sent to the file but the problem might be with actually figuring
# that out and relaying that information to the thing; so have a start_time and srate for each file I guess
# I should draw this out or something
output_files = {}


class StreamCollector:
    def __init__(self, stream_name, keep_searching=True, outfile=False):
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
            self.outfile = outfile
            if outfile:
                self.filename = str(outfile) + '.csv'
                output_files[outfile]["srate"] = min(output_files[outfile]["srate"], self.cached_stream_rate)
                output_files[outfile]["channel_count"] += self.inlet.channel_count
            else:
                self.filename = self.stream_name + '_' + datetime.datetime.now().strftime("%m-%d-%Y_%H-%M-%S") + '.csv'
        # self.resample_time_correction_rate = None # Unused method of regathering the time correction

    def collect(self, chunk_size=1):
        if self.cached_stream_rate != FOREVER:
            # Predict acceptable time for timeout
            timeout = (1 / self.cached_stream_rate) * chunk_size * TIMEOUT_ACCEPTANCE
        else:
            timeout = FOREVER

        # Have to check if outfile exists then it should output to that? nah, Imma just have it in a separate function

        if chunk_size == 1:
            data, timestamp = self.inlet.pull_sample(timeout=timeout)
            if len(timestamp) < 1:
                # If it does timeout stop running and don't record the blank sample
                self.running = False
            else:
                self.data.append((data, timestamp - self.cached_time_correction))

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

    def send_data_to_dict(self):
        if self.outfile:
            # get the outfile then get the closest timestamp
            # then clear own data
            # then eventually write something from the outfiles to the files
            # output_files[self.outfile][]
            out_keys = list(output_files[self.outfile].keys())
            out_keys.remove("srate")
            out_keys.remove("channel_count")

            out_timestamps = [int(i) for i in out_keys]
            # get closest
            # if timestamp in out_timestamps then do it; otherwise do the search
            for item in self.data:
                if item[1] in out_timestamps:
                    loc = item[1]
                else:
                    loc = closest(item[1], out_timestamps)
                # output_files[self.outfile][loc].append() # append the data straight up or not? might want channel names

            pass
        else:
            return

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


def closest_timestamp(num, timestamps, start=-1, end=-1):
    if start == -1 and end == -1:
        timestamps.sort()
        start = 0
        end = len(timestamps) - 1

    if end - start <= 1:
        if num < timestamps[start]:
            return timestamps[start - 1]
        else:
            return timestamps[start]

    mid = (start + end) // 2
    if timestamps[mid] > num:
        return closest_timestamp(num, timestamps, start, mid + 1)
    elif timestamps[mid] < num:
        return closest_timestamp(num, timestamps, mid - 1, end)
    else:
        return timestamps[mid]


# this works, but will be less efficient than binary recursive method
def closest(num, timestamps):
    timestamps.sort()
    for i in range(len(timestamps) - 1):
        if timestamps[i] < num < timestamps[i + 1]:
            if num - timestamps[i] <= timestamps[i + 1] - num:
                return timestamps[i]
            else:
                return timestamps[i + 1]


def listening_thread(stream_name, keep_searching=False, chunk_size=1, log_data=False, outfile=False):
    # Make new stream, eventually collect data from it
    stream = StreamCollector(stream_name, keep_searching, outfile)
    streams.append(stream)

    # Make sure it doesn't request invalid chunk sizes
    chunk_size = max(1, chunk_size)

    if WRITE_WITH_COUNT:
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
    else:
        # Write to file after every certain time period
        last_write = local_clock()
        while stream.running:
            data, timestamps = stream.collect(chunk_size)
            if local_clock() > last_write + TIME_BREAK:
                stream.output_csv()
                last_write = local_clock()
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

            # Get whether data should be logged to console
            if len(split_line) > 3:
                split_line[3] = split_line[3].replace(" ", "")
                listener_args.append(split_line[3].lower().startswith('t'))

            if len(split_line) > 4:
                split_line[4] = split_line[4].replace(" ", "")
                listener_args.append(split_line[4])
                # Put new filename into the list of files
                output_files[split_line[4]] = {"srate": 9999999, "channel_count": 0}
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
