import csv
from pylsl import *
import time
import datetime


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
