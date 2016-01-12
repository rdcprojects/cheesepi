import time

import pymongo
import math

from .dao import DAO
from cheesepilib.exceptions import ServerDaoError, NoSuchPeer

# What is the threshold in seconds to be considered 'active'
ACTIVE_THRESHOLD = 3600

class MongoDAO(DAO):

    def __init__(self):
        self.__init__('localhost', 27017)

    def __init__(self, host, port):
        self.client = pymongo.MongoClient()
        self.db = self.client.cheesepi

        # Initialization stuff
        # This makes sure that the peer_id field is unique and fast lookups can
        # be performed
        self.db.beacons.create_index([("last_seen",pymongo.ASCENDING)])
        self.db.tasks.create_index([("peer_id",pymongo.ASCENDING)])
        self.db.peers.create_index([("peer_id",pymongo.ASCENDING)], unique=True)
        # This (I think) ensures fast lookups for ('peer_id','results.target_id')
        self.db.peers.create_index([("peer_id",pymongo.ASCENDING),
                                   ("results.target_id",pymongo.ASCENDING)])
        self.db.peers.create_index([("peer_id",pymongo.ASCENDING),
                                   ("statistics.target_id",pymongo.ASCENDING)],
                                   unique=True)

    def close(self):
        pass # Nothing to do??

    def peer_beacon(self, peer_id, host, last_seen=0):
        if last_seen==0: last_seen=time.time()
        result = self.db.beacons.update_one(
                {'peer_id':peer_id},
                {'$set':{
                     'peer_id':peer_id,
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



    def find_peer(self, peer_id):
        result = self.db.peers.find({'peer_id':peer_id}, limit=1)
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

    def write_task(self, peer_id, task):
        result = self.db.peers.update(
                {'peer_id':peer_id},
                {'$push': {'tasks':task}}
        )
        return result

    def get_tasks(self, peer_id):
        results = self.db.tasks.find(
                {'peer_id':peer_id},
                projection={'_id':0},
                limit=5 # should be unlimited
        )
        return results

    def register_peer(self, peer_id, host):
        result = self.db.peers.update_one(
                {'peer_id':peer_id},
                {'$set':{
                     'peer_id':peer_id,
                     'host':host,
                     'tasks':[],
                     'results':[]
                     }
                },
                upsert=True
        )
        return self._return_status(result.acknowledged)

    def write_result(self, peer_id, result):
        # Can probably merge these operations into one???

        # Insert the result in the peers results-list if there is a task with a
        # matching task_id in its tasks-list
        update = self.db.peers.update(
                {
                    'peer_id':peer_id,
                    #'tasks': {
                        #'$elemMatch':{'task_id':result['task_id']}
                    #}
                },
                {'$push': {'results':result}},
                upsert=True
        )
        # Remove the task with that task_id
        #remove = self.db.peers.update(
                #{'peer_id':peer_id},
                #{'$pull': {
                    #'tasks':{'task_id':result['task_id']}
                    #}
                #}
        #)
        return self._return_status(update['updatedExisting'])

    def write_ping_results(self, peer_id, target_id, results):

        ALPHA = 0.5 # Weight for calculating mean and variance

        stats = self.db.peers.find({
                'peer_id':peer_id,
                'statistics.target_id':target_id
            },
        )

        mean_delay_value = 0
        mean_delay_variance = 0
        average_median_delay_value = 0
        average_median_delay_variance = 0
        average_packet_loss_value = 0
        average_packet_loss_variance = 0

        if stats.count() > 0:
            # TODO THIS IS UGLY AS HELL... remember to clean it up into something
            # more sane....
            try:
                old_stats = stats[0]['statistics'][0]['ping']
            except Exception as e:
                print("No stats for ping available.")
            try:
                mean_delay_value = old_stats['mean_delay']['value']
            except Exception as e:
                print("No mean for ping available.")
            try:
                mean_delay_variance = old_stats['mean_delay']['variance']
            except Exception as e:
                print("No variance for ping available.")
            try:
                average_median_delay_value = old_stats['average_median_delay']['value']
            except Exception as e:
                print("No average_median for ping available.")
            try:
                average_median_delay_variance = old_stats['average_median_delay']['variance']
            except Exception as e:
                print("No variance for ping available.")
            try:
                average_packet_loss_value = old_stats['average_packet_loss']['value']
            except Exception as e:
                print("No mean for ping available.")
            try:
                average_packet_loss_variance = old_stats['average_packet_loss']['variance']
            except Exception as e:
                print("No variance for ping available.")
        else:
            # No previous stats
            self.db.peers.insert(
                    {'peer_id':peer_id,
                     'statistics':[{'target_id':target_id}]}
            )

        probe_count = 0
        packet_loss = 0
        max_rtt = 0
        min_rtt = 999999999
        avg_rtt = 0

        from cheesepilib.server.processing.utils import StatObject, median

        mean_delay = StatObject(mean_delay_value, mean_delay_variance)
        average_median_delay = StatObject(average_median_delay_value, average_median_delay_variance)
        average_packet_loss = StatObject(average_packet_loss_value, average_packet_loss_variance)

        for result in results:
            probe_count = probe_count + result['value']['probe_count']
            packet_loss = packet_loss + result['value']['packet_loss']
            max_rtt = max(max_rtt, result['value']['max_rtt'])
            min_rtt = min(min_rtt, result['value']['min_rtt'])
            avg_rtt = result['value']['avg_rtt']

            # TODO this is done because the sequence is stored as a string
            # representation of a list, should be changed in the future so that
            # it's a list from the start
            import ast
            delay_sequence = ast.literal_eval(result['value']['delay_sequence'])

            mean_delay.add_datum(avg_rtt)
            average_median_delay.add_datum(median(delay_sequence))
            average_packet_loss.add_datum(packet_loss/probe_count)

            update = self.db.peers.update(
                    {
                        'peer_id':peer_id,
                    },
                    {'$push': {'results':result}},
                    upsert=True
            )


        # Find the element in the statistics array for the peer where the
        # target id matches, then update the stats accordingly
        update_result = self.db.peers.update_one(
                {'peer_id':peer_id,
                 'statistics.target_id':target_id
                },
                {'$inc':{
                    'statistics.$.ping.total_probe_count':probe_count,
                    'statistics.$.ping.total_packet_loss':packet_loss
                    },
                 '$max':{'statistics.$.ping.all_time_max_rtt':max_rtt},
                 '$min':{'statistics.$.ping.all_time_min_rtt':min_rtt},
                 '$set':{
                    'statistics.$.ping.mean_delay.value':mean_delay.mean,
                    'statistics.$.ping.mean_delay.variance':mean_delay.variance,
                    'statistics.$.ping.mean_delay.std_dev':mean_delay.std_dev,
                    'statistics.$.ping.average_median_delay.value':average_median_delay.mean,
                    'statistics.$.ping.average_median_delay.variance':average_median_delay.variance,
                    'statistics.$.ping.average_median_delay.std_dev':average_median_delay.std_dev,
                    'statistics.$.ping.average_packet_loss.value':average_packet_loss.mean,
                    'statistics.$.ping.average_packet_loss.variance':average_packet_loss.variance,
                    'statistics.$.ping.average_packet_loss.std_dev':average_packet_loss.std_dev,
                  },
                },
                upsert=True
        )

        return self._return_status(update_result.modified_count>0)

    def purge_results(self, peer_id):
        result = self.db.peers.update(
                {'peer_id':peer_id},
                {'results':[]}
        )
        return result

    def purge_results_older_than(self, peer_id, timestamp):
        result = self.db.peers.update(
                {'peer_id':peer_id},
                {'$pull': {
                    'results':{
                        'timestamp':{'$lt': timestamp}
                        }
                    }
                }
        )
        return result

