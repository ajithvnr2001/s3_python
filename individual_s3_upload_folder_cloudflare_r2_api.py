# upload folders using Cloudflare R2
import os
import time
from datetime import timedelta
import boto3
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig
from botocore.client import Config

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================
ACCOUNT_ID = 'ID'           # Your Cloudflare Account ID
ACCESS_KEY_ID = 'KEY'        # R2 API Access Key ID
SECRET_ACCESS_KEY = 'KEY'    # R2 API Secret Access Key
BUCKET_NAME = 'Bucket'         # Your R2 bucket name
FOLDER_PATH = '/content/3'                     # Folder to upload from

# Initialize S3 client for Cloudflare R2
s3 = boto3.client(
    service_name='s3',
    endpoint_url=f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com',
    aws_access_key_id=ACCESS_KEY_ID,
    aws_secret_access_key=SECRET_ACCESS_KEY,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

# Global progress tracking variables
bytes_transferred = 0
total_bytes = 0
start_time = 0
last_print_time = 0

def progress_callback(new_bytes):
    """Callback function for upload progress"""
    global bytes_transferred, start_time, last_print_time
    bytes_transferred += new_bytes
    
    # Print progress every second to avoid overwhelming output
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
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket '{BUCKET_NAME}' already exists.\n")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                # For R2, region is 'auto' - bucket creation is simple
                s3.create_bucket(Bucket=BUCKET_NAME)
                print(f"Bucket '{BUCKET_NAME}' created successfully.\n")
            except ClientError as create_error:
                print(f"Failed to create bucket: {create_error}")
        else:
            print(f"Error checking bucket: {e}")

def upload_files():
    """Upload all files from the specified folder"""
    global start_time, total_bytes, bytes_transferred, last_print_time
    uploaded_files = []
    
    # Configure multipart upload settings
    config = TransferConfig(
        multipart_threshold=8 * 1024 * 1024,  # 8MB
        max_concurrency=10,
        multipart_chunksize=8 * 1024 * 1024,
        use_threads=True
    )
    
    # Get list of files to upload
    files_to_upload = []
    for item_name in os.listdir(FOLDER_PATH):
        item_path = os.path.join(FOLDER_PATH, item_name)
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
            # Upload without ACL parameter (R2 doesn't support ACLs)
            s3.upload_file(
                item_path,
                BUCKET_NAME,
                item_name,
                Config=config,
                Callback=progress_callback
            )
            print(f'\n✓ Successfully uploaded {item_name}\n')
            uploaded_files.append(item_name)
        except ClientError as e:
            print(f"\n✗ Failed to upload {item_name}: {e}\n")
    
    return uploaded_files

def generate_presigned_urls(file_names, expiration=604800):
    """Generate presigned URLs for 7-day access (604800 seconds = 7 days max)"""
    presigned_urls = []
    for file_name in file_names:
        try:
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': BUCKET_NAME, 'Key': file_name},
                ExpiresIn=expiration  # 7 days maximum for R2
            )
            presigned_urls.append((file_name, url))
        except ClientError as e:
            print(f"Error generating presigned URL for {file_name}: {e}")
    return presigned_urls

# Main execution
if __name__ == "__main__":
    print("=" * 70)
    print("Cloudflare R2 Storage Uploader")
    print("=" * 70)
    print(f"Folder: {FOLDER_PATH}")
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Endpoint: https://{ACCOUNT_ID}.r2.cloudflarestorage.com")
    print("=" * 70 + "\n")
    
    create_bucket_if_not_exists()
    uploaded_files = upload_files()
    
    if uploaded_files:
        print("\n" + "=" * 70)
        print(f"✓ Successfully uploaded {len(uploaded_files)} file(s)!")
        print("=" * 70 + "\n")
        
        # Generate presigned URLs valid for 7 days
        print("Presigned URLs (valid for 7 days):")
        print("-" * 70)
        presigned_urls = generate_presigned_urls(uploaded_files, expiration=604800)
        for file_name, url in presigned_urls:
            print(f"{file_name}:\n{url}\n")
        
        print("=" * 70)
        print("NOTE: These URLs will expire in 7 days.")
        print("Re-run the script to generate new URLs if needed.")
        print("=" * 70)
    else:
        print("\n✗ No files were uploaded.")
