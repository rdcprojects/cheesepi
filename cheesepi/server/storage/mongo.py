import time

import logging
import pymongo
import math

from .dao import DAO
from cheesepi.exceptions import ServerDaoError, NoSuchPeer

from cheesepi.server.storage.models.statistics import StatisticsSet
from cheesepi.server.storage.models.entity import Entity, PeerEntity, LandmarkEntity

# What is the threshold in seconds to be considered 'active'
ACTIVE_THRESHOLD = 3600

class MongoDAO(DAO):
	log = logging.getLogger("cheesepi.server.storage.MongoDAO")

	def __init__(self, host='localhost', port=27017):
		self.client = pymongo.MongoClient()
		self.db = self.client.cheesepi

		# Initialization stuff
		# This makes sure that the uuid field is unique and fast lookups can
		# be performed
		self.db.beacons.create_index([("last_seen",pymongo.ASCENDING)])
		self.db.tasks.create_index([("uuid",pymongo.ASCENDING)])
		self.db.entities.create_index([("uuid",pymongo.ASCENDING)], unique=True)
		self.db.peers.create_index([("uuid",pymongo.ASCENDING)], unique=True)
		# This (I think) ensures fast lookups for ('uuid','results.target_id')
		self.db.peers.create_index([("uuid",pymongo.ASCENDING),
		                            ("results.target_id",pymongo.ASCENDING)])
		self.db.peers.create_index([("uuid",pymongo.ASCENDING),
		                            ("statistics.target_id",pymongo.ASCENDING)])

	def close(self):
		pass # Nothing to do??

	def get_bulk_writer(self):
		return self.db.peers.initialize_ordered_bulk_op()

	def peer_beacon(self, uuid, host, last_seen=0):
		if last_seen==0: last_seen=time.time()
		result = self.db.beacons.update_one(
			{'uuid':uuid},
			{'$set':{
				'uuid':uuid,
				'host':host,
				'last_seen':last_seen,
				}
			},
			upsert=True
		)
		return self._return_status(result.acknowledged)

	def active_peers(self, since=0):
		if since<=0: since=time.time()-ACTIVE_THRESHOLD
		result = self.db.beacons.find({"last_seen": {"$gt": since}})
		return result

	def find_peer(self, uuid):
		result = self.db.peers.find({'uuid':uuid}, limit=1)
		if result.count() > 0:
			return result
		else:
			raise NoSuchPeer()

	def get_peers(self):
		result = self.db.peers.find()
		return result

	def get_random_peer(self):
		from random import randint
		num_peers = self.db.peers.count()
		#print("{} peers in collection".format(num_peers))
		result = self.db.peers.find(limit=1, skip=randint(0,num_peers))
		if result.count() > 0:
			peer = result.next()
			return peer
		else:
			# What does this mean????
			raise ServerDaoError()

	def write_task(self, uuid, task):
		result = self.db.peers.update(
			{'uuid':uuid},
			{'$push': {'tasks':task}}
		)
		return result

	def get_tasks(self, uuid):
		results = self.db.tasks.find(
			{'uuid':uuid},
			projection={'_id':0},
			limit=5 # should be unlimited
		)
		return results

	def register_peer_entity(self, entity):
		"""
		"""
		assert isinstance(entity, PeerEntity)
		result = self.db.entities.update_one(
			{'uuid':entity.get_uuid()},
			{'$set':entity.toDict()},
			upsert=True
		)
		return self._return_status(result.acknowledged)

	def get_random_entity(self, ignore_uuid=None):
		import re
		from random import randint

		if ignore_uuid is not None:
			query = {'uuid': { '$not': re.compile(ignore_uuid) } }
		else:
			query = {}

		#self.log.info("UUID: {}".format(ignore_uuid))
		#self.log.info("Query: {}".format(query))
		#num_entities = self.db.entities.count()
		#self.log.info("{} entities in collection".format(num_entities))

		cursor = self.db.entities.find(query)
		skipcount = randint(0, cursor.count()-1)
		#self.log.info("skipcount: {}".format(skipcount))
		cursor.skip(skipcount) # skip the first skipcount elements
		cursor.limit(-1) # pick the last element

		#self.log.info("{}".format(cursor))
		#self.log.info("Cursor count: {}".format(cursor.count()))

		if cursor.count() > 0 and cursor.alive:
			#self.log.info("alive? {}".format(cursor.alive))
			#self.log.info("\n{}".format(cursor.mystats()))
			entity = cursor.next()
			entity_obj = Entity.fromDict(entity)
			return entity_obj
		else:
			# What does this mean????
			raise ServerDaoError()

	def write_result(self, uuid, result):
		# Can probably merge these operations into one???

		# Insert the result in the peers results-list if there is a task with a
		# matching task_id in its tasks-list
		update = self.db.peers.update(
			{
				'uuid':uuid,
				#'tasks': {
					#'$elemMatch':{'task_id':result['task_id']}
				#}
			},
			{'$push': {'results':result}},
			upsert=True
		)
		# Remove the task with that task_id
		#remove = self.db.peers.update(
			#{'uuid':uuid},
			#{'$pull': {
				#'tasks':{'task_id':result['task_id']}
				#}
			#}
		#)
		return self._return_status(update['updatedExisting'])




	def get_all_stats(self, uuid):
		return self.get_stats_set_for_targets(uuid, None)
	def get_stats_set(self, uuid, target):
		"""
		Returns a StatisticsSet object loaded with all the statistics
		for measurements from peer uuid to target.

		Args:
			uuid: a peer uuid
			target: a Entity object
		Returns:
			A StatisticsSet object if query is successful, None
			otherwise.
		"""
		return self.get_stats_set_for_targets(uuid, [target])

	def get_stats_set_for_results(self, uuid, results):
		"""
		Returns a StatisticsSet object loaded with all the statistics
		for measurements from peer uuid to all targets that concern the
		results in the result list.

		Args:
			uuid: a peer uuid
			results: a list of Result objects
		Returns:
			A StatisticsSet object if query is successful, None
			otherwise.
		"""
		targets = [result.get_target() for result in results]

		return self.get_stats_set_for_targets(uuid, targets)

	def get_stats_set_for_targets(self, uuid, targets):
		"""
		Returns a StatisticsSet object loaded with all the statistics for
		measurements from uuid to all targets in the targets list.

		Args:
			uuid: a peer uuid
			targets: a list of Entity objects
		Returns:
			A StatisticsSet object if query is successful, None
			otherwise.
		"""

		projection = None

		if targets is not None:
			projection = {}
			for target in targets:
				key = "statistics.{}".format(target.get_uuid())
				projection[key] = 1

		stats = self.db.peers.find(
			{'uuid':uuid},
			projection,
		)

		# Should be unique so can only ever find one
		if stats.count() > 0:
			#self.log.info(stats[0])
			return StatisticsSet.fromDict(stats[0]['statistics'])
		else:
			return StatisticsSet()

	def write_stats_set(self, uuid, statistics_set):
		"""
		Write a statistics set object to the database.

		Args:
			uuid: a peer uuid
			statistcs_set: a StatisticsSet object
		Returns:
			the result from the write operation
		"""
		bulk_writer = self.db.peers.initialize_ordered_bulk_op()

		bulk_writer = self.bulk_write_stats_set(bulk_writer, uuid,
		                                        statistics_set)

		result = bulk_writer.execute()
		self.log.info("Wrote statistics set with result: {}".format(result))
		return result

	def bulk_write_stats_set(self, bulk_writer, uuid, statistics_set):
		"""
		Queue writing of a StatisticsSet object to a bulk writer object.

		Args:
			bulk_writer: a bulk writer object
			uuid: a peer uuid
			statistcs_set: a StatisticsSet object
		Returns:
			the modified bulk writer object
		"""
		#self.log.info("IN WRITE_STATS")

		prefix_key = "statistics" #.format(target.get_uuid())

		stat_object = {}
		#self.log.info(statistics_set)

		for stat in statistics_set:
			stat_target_uuid = stat.get_target().get_uuid()
			#stat_type = stat.get_type()
			#if stat_target_uuid not in stat_object:
				#stat_object[stat_target_uuid] = {}
			#stat_object[stat_target_uuid][stat_type] = stat.toDict()

			key = "{}.{}".format(prefix_key, stat_target_uuid)

			bulk_writer.find(
				{'uuid':uuid}
				).upsert(
				).update_one(
				{'$set':{
					key:{
						stat.get_type():stat.toDict(),
						},
					}
				},
			)
		#self.log.info("EXITING WRITE_STATS")

		return bulk_writer

	def write_results(self, uuid, results):
		"""
		Writes a list of results from a peer to the database.

		Args:
			uuid: a peer uuid
			results: a list of Result objects
		Returns:
			the result of the write operation
		"""
		bulk_writer = self.db.peers.initialize_ordered_bulk_op()

		bulk_writer = self.bulk_write_results(bulk_writer, uuid, results)

		result = bulk_writer.execute()
		self.log.info("Wrote a list of results objects with result: {}".format(result))
		return result

	def bulk_write_results(self, bulk_writer, uuid, results):
		"""
		Queue writing of a list of Result objects to a bulk writer
		object.

		Args:
			bulk_writer: a bulk writer object
			uuid: a peer uuid
			results: a list of Result objects
		Returns:
			the modified bulk writer object
		"""
		for result in results:
			bulk_writer.find(
				{'uuid':uuid}
				).upsert(
				).update(
				{'$push': {'results':result.toDict()}}
			)
		return bulk_writer

	def purge_results(self, uuid):
		result = self.db.peers.update(
			{'uuid':uuid},
			{'results':[]}
		)
		return result

	def purge_results_older_than(self, uuid, timestamp):
		result = self.db.peers.update(
			{'uuid':uuid},
			{'$pull': {
				'results':{
					'timestamp':{'$lt': timestamp}
					}
				}
			}
		)
		return result
