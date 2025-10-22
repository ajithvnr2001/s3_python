import os
import time
from datetime import timedelta
from urllib.parse import quote
import boto3
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig
# INPUT ACTUAL VALUES IN "VALUE"
# Set these BEFORE importing boto3
os.environ['AWS_REQUEST_CHECKSUM_CALCULATION'] = 'when_required'
os.environ['AWS_RESPONSE_CHECKSUM_VALIDATION'] = 'when_required'

# Initialize S3 client for Oracle Cloud Infrastructure
namespace = 'VALUE'
region = 'ap-hyderabad-1'

s3 = boto3.client(
    service_name='s3',
    aws_access_key_id='VALUE',
    aws_secret_access_key='VALUE',
    endpoint_url=f'https://{namespace}.compat.objectstorage.{region}.oraclecloud.com',
    region_name=region
)

# Set the folder path and bucket name
folder_path = '/content/3'
bucket_name = 'VALUE'

# Global progress tracking variables
bytes_transferred = 0
total_bytes = 0
start_time = 0
last_print_time = 0

def progress_callback(new_bytes):
    """Callback function for upload progress"""
    global bytes_transferred, start_time, last_print_time
    bytes_transferred += new_bytes
    
    current_time = time.time()
    if current_time - last_print_time >= 1.0:
        elapsed_time = max(current_time - start_time, 0.001)
        speed = (bytes_transferred / (1024 ** 2)) / elapsed_time
        remaining_bytes = total_bytes - bytes_transferred
        
        if bytes_transferred > 0:
            estimated_seconds = remaining_bytes / (bytes_transferred / elapsed_time)
            estimated_remaining_time = str(timedelta(seconds=int(estimated_seconds)))
        else:
            estimated_remaining_time = "Unknown"
        
        print(f'\rUploaded: {bytes_transferred / (1024 ** 3):.2f}/{total_bytes / (1024 ** 3):.2f} GB, '
              f'Speed: {speed:.2f} MB/s, '
              f'Estimated remaining time: {estimated_remaining_time}', end='', flush=True)
        
        last_print_time = current_time

def create_bucket_if_not_exists():
    """Create bucket if it doesn't exist"""
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"Bucket '{bucket_name}' already exists.\n")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                s3.create_bucket(Bucket=bucket_name)
                print(f"Bucket '{bucket_name}' created successfully.\n")
            except ClientError as create_error:
                print(f"Failed to create bucket: {create_error}")
        else:
            print(f"Error checking bucket: {e}")

def upload_files():
    """Upload all files from the specified folder"""
    global start_time, total_bytes, bytes_transferred, last_print_time
    uploaded_files = []
    
    config = TransferConfig(
        multipart_threshold=8 * 1024 * 1024,
        max_concurrency=10,
        multipart_chunksize=8 * 1024 * 1024,
        use_threads=True
    )
    
    files_to_upload = []
    for item_name in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item_name)
        if os.path.isfile(item_path):
            files_to_upload.append((item_name, item_path))
    
    if not files_to_upload:
        print("No files found to upload.")
        return uploaded_files
    
    print(f"Found {len(files_to_upload)} file(s) to upload.\n")
    
    for item_name, item_path in files_to_upload:
        print(f"Uploading {item_name}...")
        
        file_size = os.path.getsize(item_path)
        total_bytes = file_size
        bytes_transferred = 0
        start_time = time.time()
        last_print_time = start_time
        
        try:
            s3.upload_file(
                item_path,
                bucket_name,
                item_name,
                Config=config,
                Callback=progress_callback
            )
            print(f'\n✓ Successfully uploaded {item_name}\n')
            uploaded_files.append(item_name)
        except ClientError as e:
            print(f"\n✗ Failed to upload {item_name}: {e}\n")
    
    return uploaded_files

def generate_public_urls(file_names):
    """
    Generate public URLs for OCI Object Storage
    Format: https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket}/o/{object}
    Note: Bucket must be public for these URLs to work
    """
    public_urls = []
    for file_name in file_names:
        # URL encode the file name to handle spaces and special characters
        encoded_name = quote(file_name, safe='')
        url = f"https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket_name}/o/{encoded_name}"
        public_urls.append((file_name, url))
    return public_urls

def generate_presigned_urls(file_names, expiration=604800):
    """Generate presigned URLs for 7-day access (604800 seconds = 7 days)"""
    presigned_urls = []
    for file_name in file_names:
        try:
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_name},
                ExpiresIn=expiration
            )
            presigned_urls.append((file_name, url))
        except ClientError as e:
            print(f"Error generating presigned URL for {file_name}: {e}")
    return presigned_urls

# Main execution
if __name__ == "__main__":
    print("=" * 70)
    print("Oracle Cloud Infrastructure Object Storage Uploader")
    print("=" * 70)
    print(f"Folder: {folder_path}")
    print(f"Bucket: {bucket_name}")
    print(f"Namespace: {namespace}")
    print(f"Region: {region}")
    print(f"Endpoint: https://{namespace}.compat.objectstorage.{region}.oraclecloud.com")
    print("=" * 70 + "\n")
    
    create_bucket_if_not_exists()
    uploaded_files = upload_files()
    
    if uploaded_files:
        print("\n" + "=" * 70)
        print(f"✓ Successfully uploaded {len(uploaded_files)} file(s)!")
        print("=" * 70 + "\n")
        
        # Generate public URLs
        print("Public URLs (permanent - requires public bucket):")
        print("-" * 70)
        public_urls = generate_public_urls(uploaded_files)
        for file_name, url in public_urls:
            print(f"{file_name}:\n{url}\n")
        
        print("=" * 70 + "\n")
        
        # Generate presigned URLs
        print("Presigned URLs (valid for 7 days - works with private bucket):")
        print("-" * 70)
        presigned_urls = generate_presigned_urls(uploaded_files, expiration=604800)
        for file_name, url in presigned_urls:
            print(f"{file_name}:\n{url}\n")
        
        print("=" * 70)
        print("NOTE:")
        print("• Public URLs are permanent but require the bucket to be public")
        print("• Presigned URLs expire in 7 days but work with private buckets")
        print("=" * 70)
    else:
        print("\n✗ No files were uploaded.")
