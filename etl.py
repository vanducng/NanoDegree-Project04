import os
import configparser
from datetime import datetime
from pyspark.sql.types import *
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf

config = configparser.ConfigParser()
config.read("dl.cfg")

os.environ["AWS_ACCESS_KEY_ID"]=config["AWS"]["AWS_ACCESS_KEY_ID"]
os.environ["AWS_SECRET_ACCESS_KEY"]=config["AWS"]["AWS_SECRET_ACCESS_KEY"]

def create_spark_session():
    """
    Create spark session on AWS
    """
    spark = SparkSession \
        .builder \
        .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:2.7.0") \
        .getOrCreate()
    return spark


def process_song_data(spark, input_data, output_data):
    """
    Description: This functions is to load the song logs from S3, then processes on EMR or EC2 then store back to S3 for further usage

    Parameters:
        spark       : spark session
        input_data  : where the song json files located
        output_data : where to store the output files after completing process input files
    """
    # get filepath to song data file
    song_data = input_data + "song_data/*/*/*/*.json"
    
    # read song data file
    songs_df = spark.read.json(song_data)

    # Create temp view for querying
    songs_df.createOrReplaceTempView("songs")

    # extract columns to create songs table
    songs_table = spark.sql("""
                            SELECT song_id, 
                            title,
                            artist_id,
                            year,
                            duration
                            FROM songs
                            """) 
    
    # write songs table to parquet files partitioned by year and artist
    songs_table.write.mode("overwrite").partitionBy("year", "artist_id").parquet(output_data + "songs")

    # extract columns to create artists table
    artists_table = spark.sql("""
                            SELECT DISTINCT artist_id,
                            artist_name name,
                            artist_location location,
                            artist_latitude latitude,
                            artist_longitude longitude
                            FROM songs
                            """)
    
    # write artists table to parquet files
    artists_table.write.mode("overwrite").parquet(output_data + "artists")


def process_log_data(spark, input_data, output_data):
    """
    Description: This functions is to load the user logs from S3, then processes on EMR or EC2 then store back to S3 for further usage

    Parameters:
        spark       : spark session
        input_data  : where the song json files located
        output_data : where to store the output files after completing process input files
    """
    # get filepath to log data file
    log_data = input_data + "log_data/*.json"

    # read log data file
    logs_df = spark.read.json(log_data)
    
    # filter by actions for song plays
    logs_df = logs_df.filter(logs_df["page"] == "NextSong")

    # Create temp view used for SQL query
    logs_df.createOrReplaceTempView("logs")

    # extract columns for users table    
    users_table = spark.sql("""
                    SELECT DISTINCT userId user_id,
                    firstName first_name,
                    lastName last_name,
                    gender,
                    level
                    FROM logs
                    WHERE TRIM(userId) <> ''
                """)
    
    # write users table to parquet files
    users_table.write.mode("overwrite").parquet(output_data + "users")

    # create timestamp column from original timestamp column
    get_timestamp = udf(lambda x: datetime.fromtimestamp(x/1000), TimestampType())
    logs_df = logs_df.withColumn("timestamp", get_timestamp(logs_df.ts))
    
    # Create temp view for timestamp for query
    logs_df.select("timestamp").createOrReplaceTempView("time")

    # extract columns to create time table
    time_table = spark.sql("""
                    SELECT DISTINCT timestamp start_time,
                    HOUR(timestamp) hour,
                    DAYOFMONTH(timestamp) day,
                    WEEKOFYEAR(timestamp) week,
                    MONTH(timestamp) month,
                    YEAR(timestamp) year,
                    DAYOFWEEK(timestamp) weekday
                    FROM time
                    """)
    
    # write time table to parquet files partitioned by year and month
    time_table.write.mode("overwrite").partitionBy("year", "month").parquet(output_data + "time")

    # Create temp view used for SQL query, this call is updated with timestamp column
    logs_df.createOrReplaceTempView("logs")

    # Load songs table
    songs_df = spark.read.parquet(output_data + "songs")
    songs_df.createOrReplaceTempView("songs")

    # Load artists table
    artists_df = spark.read.parquet(output_data + "artists")
    artists_df.createOrReplaceTempView("artists") 

    # extract columns from joined song and log datasets to create songplays table 
    songplays_table = spark.sql("""
                        SELECT monotonically_increasing_id() songplay_id,
                        l.timestamp start_time,
                        l.userId user_id,
                        s.song_id,
                        a.artist_id,
                        l.sessionId session_id,
                        l.location,
                        l.userAgent user_agent,
                        MONTH(l.timestamp) month,
                        YEAR(l.timestamp) year
                        FROM logs l
                        INNER JOIN songs s ON s.title = l.song AND s.duration = l.length
                        INNER JOIN artists a ON a.artist_id = s.artist_id AND a.name = l.artist
                        """)

    # write songplays table to parquet files partitioned by year and month
    songplays_table.write.mode("overwrite").partitionBy("year", "month").parquet(output_data + "songplays")


def main():
    spark = create_spark_session()
    input_data = "s3a://udacity-dend/"
    output_data = "s3a://udacity-dend/output/"
    
    process_song_data(spark, input_data, output_data)    
    process_log_data(spark, input_data, output_data)


if __name__ == "__main__":
    main()
