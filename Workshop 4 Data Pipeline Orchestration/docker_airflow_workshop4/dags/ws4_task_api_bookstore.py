from airflow.models import DAG
from airflow.decorators import dag, task
from airflow.operators.python import PythonOperator
from airflow.providers.mysql.hooks.mysql import MySqlHook
from airflow.utils.dates import days_ago
import pandas as pd
import requests
import sqlalchemy


MYSQL_CONNECTION = "mysql_default" 
CONVERSION_RATE_URL = "https://r2de2-workshop-vmftiryt6q-ts.a.run.app/usd_thb_conversion_rate"


mysql_output_path = "/home/airflow/data/audible_data_merged.csv"
conversion_rate_output_path = "/home/airflow/data/conversion_rate.csv"
final_output_path = "/home/airflow/data/final_databook.csv"


default_args = {
    'owner': 'zunkiflee',
}

@dag(default_args=default_args, schedule_interval='@once', start_date=days_ago(1), tags=['workshop_pipeline'])
def book_pipeline():

    @task
    def get_data_from_mysql(output_path):

        mysqlserver = MySqlHook(MYSQL_CONNECTION)

        # query data from database
        audible_data = mysqlserver.get_pandas_df(sql="SELECT * FROM audible_data")
        audible_transaction = mysqlserver.get_pandas_df(sql="SELECT * FROM audible_transaction")

        # merge audible_data and audible_transaction
        df = audible_transaction.merge(audible_data, how="left", left_on="book_id", right_on="Book_ID")

        # save file .csv
        df.to_csv(output_path, index=False)
        print(f"Output to {output_path}")

    @task
    def get_conversion_rate(output_path):
        
        r = requests.get(CONVERSION_RATE_URL)
        result_conversion_rate = r.json()
        data_conversion_rate = pd.DataFrame(result_conversion_rate)

        data_conversion_rate = data_conversion_rate.reset_index().rename(columns={'index':'date'})
        data_conversion_rate.to_csv(output_path, index=False)
        print(f'Output to {output_path}')

    @task
    def merge_data(transaction_path, conversion_rate_path, output_path):
        transaction = pd.read_csv(transaction_path)
        conversion_rate = pd.read_csv(conversion_rate_path)

        # สร้างคอลัมน์ใหม่ data ใน transaction
        # แปลง transaction['date'] เป็น timestamp
        transaction['date'] = transaction['timestamp']
        transaction['date'] = pd.to_datetime(transaction['date']).dt.date
        conversion_rate['date'] = pd.to_datetime(conversion_rate['date']).dt.date

        # merge 2 datframe transaction, conversion_rate
        final_databook = transaction.merge(conversion_rate,
                                            how='left',
                                            left_on='date',
                                            right_on='date')
        
        # ลบเครื่องหมาย $ ในคอลัมน์ Price และแปลงเป็น float
        final_databook['Price'] = final_databook.apply(lambda x: x['Price'].replace('$',''), axis=1)
        final_databook['Price'] = final_databook['Price'].astype(float)

        # สร้างคอลัมน์ใหม่ชื่อว่า THBPrice เอา price * conversion_rate
        final_databook['THBPrice'] = final_databook['Price'] * final_databook['conversion_rate']
        final_databook = final_databook.drop(['date', 'book_id'], axis=1)

        # save ไฟล์ fianl_databook เป็น csv
        final_databook.to_csv(output_path, index=False)
        print(f"Output to {output_path}")

    
    t1 = get_data_from_mysql(output_path=mysql_output_path)
    t2 = get_conversion_rate(output_path=conversion_rate_output_path)
    t3 = merge_data(
            transaction_path=mysql_output_path, 
            conversion_rate_path=conversion_rate_output_path, 
            output_path=final_output_path)

    [t1, t2] >> t3

book_pipeline()                            