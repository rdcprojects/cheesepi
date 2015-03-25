#!/bin/bash

#Get all available sql-dumps
ARRAY=()
for f in $(ls /home/pi/Buffer/[^alldata]*sql); do
	ARRAY+=($f)
done

COUNT=${#ARRAY[@]} 

#Create the command to merge them into one file
if [ $COUNT -eq 0 ]; then
	exit 0
elif [ $COUNT -eq 1 ]; then
	cp ${ARRAY[{1}]} alldata.sql
	echo "1"
else
	FIRST=${ARRAY[${1}]} #one-indexed? wtf
	REST=""
	for (( i=1;i<COUNT;i++)); do
		REST+=${ARRAY[${i}]}
		REST+=" "
	done

	( cat $FIRST ; cat $REST | sed -e '/^DROP TABLE/,/^-- Dumping data/d' ) > alldata.sql

fi

#Dump into SQL

mysql -u push buffer < alldata.sql

#Probably move old files here