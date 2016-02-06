from __future__ import unicode_literals, absolute_import, print_function

import logging
import heapq
import random

from cheesepi.server.storage.mongo import MongoDAO
from .Scheduler import Scheduler

BLIND_SCHEDULE_RATIO=float(1)/float(3)

class PingScheduler(Scheduler):

	log = logging.getLogger("cheesepi.server.scheduling.PingScheduler")

	def __init__(self, uuid):
		self.dao = MongoDAO('localhost', 27017)
		self._uuid = uuid

	def get_schedule(self, num=1):
		from pprint import pformat

		#self.log.info("Generating schedule with blind ratio = {}".format(
			#BLIND_SCHEDULE_RATIO))

		# num is 1, we randomize if it will be random or not to achieve full coverage
		if num == 1:
			x = random.uniform(0.0, 1.0)
			if x <= BLIND_SCHEDULE_RATIO:
				non_blind_num = 0
			else:
				non_blind_num = 1
		else:
			non_blind_num = int(num - (num*BLIND_SCHEDULE_RATIO))

		blind_num = num - non_blind_num

		#self.log.info("Non blinds = {}".format(non_blind_num))

		schedule = []
		stats = self.dao.get_all_stats(self._uuid)
		#self.log.info(pformat(stats.toDict()))

		priority_sorted_targets = []

		for s in stats:
			#print(pformat(s.toDict()))
			delay_variance = s.get_delay().get_variance()
			target = s.get_target()
			#print(target)
			#print(delay_variance)
			heapq.heappush(priority_sorted_targets, (-delay_variance, target))

		#print(priority_sorted_targets)

		for i in range(0, min(non_blind_num,len(priority_sorted_targets))):
			target = heapq.heappop(priority_sorted_targets)
			schedule.append(target[1])

		if len(schedule) < non_blind_num:
			# schedule length needs to be filled with more blinds
			blind_num = blind_num + (non_blind_num - len(schedule))

		for i in range(0, blind_num):
			#self.log.info("Adding blind to schedule")
			entity = self.dao.get_random_entity(ignore_uuid=self._uuid)
			schedule.append(entity)

		return schedule


if __name__ == "__main__":
	import argparse
	import cheesepi.server.utils as utils

	utils.init_logging()

	parser = argparse.ArgumentParser()
	parser.add_argument('--id', type=str, default=None)
	parser.add_argument('--num', type=int, default=1)

	args = parser.parse_args()

	ps = PingScheduler(args.id)

	schedule = ps.get_schedule(num=args.num)
	if len(schedule) == 0:
		print("Nothing scheduled")
	else:
		for target in schedule:
			print(target.get_uuid())
