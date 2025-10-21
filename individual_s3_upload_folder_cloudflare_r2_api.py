# upload folders using Cloudflare R2 with 10GB free tier limit check
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
ACCOUNT_ID = 'id'           # Your Cloudflare Account ID
ACCESS_KEY_ID = 'id'        # R2 API Access Key ID
SECRET_ACCESS_KEY = 'id'    # R2 API Secret Access Key
BUCKET_NAME = 'bucket'         # Your R2 bucket name
FOLDER_PATH = '/content/3'  # Folder to upload from
MAX_TOTAL_SIZE_GB = 9.5     # Maximum total size in GB (Cloudflare free tier with safety margin)

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

def get_bucket_size():
    """Calculate total size of all files in the bucket"""
    total_size = 0
    file_count = 0
    
    try:
        # List all objects in the bucket
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=BUCKET_NAME)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    total_size += obj['Size']
                    file_count += 1
        
        return total_size, file_count
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            return 0, 0
        else:
            print(f"Error getting bucket size: {e}")
            return 0, 0

def get_local_files_size(folder_path):
    """Calculate total size of files to be uploaded"""
    total_size = 0
    files_to_upload = []
    
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return 0, []
    
    for item_name in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item_name)
        if os.path.isfile(item_path):
            file_size = os.path.getsize(item_path)
            total_size += file_size
            files_to_upload.append((item_name, item_path, file_size))
    
    return total_size, files_to_upload

def check_size_limit(existing_size, new_files_size):
    """Check if total size would exceed the 10GB limit"""
    max_size_bytes = MAX_TOTAL_SIZE_GB * 1024 ** 3  # Convert GB to bytes
    total_size = existing_size + new_files_size
    
    print("=" * 70)
    print("SIZE CHECK (Cloudflare R2 Free Tier - 10GB Limit)")
    print("=" * 70)
    print(f"Existing files in bucket: {existing_size / (1024 ** 3):.4f} GB")
    print(f"New files to upload:      {new_files_size / (1024 ** 3):.4f} GB")
    print(f"Total size would be:      {total_size / (1024 ** 3):.4f} GB")
    print(f"Maximum allowed:          {MAX_TOTAL_SIZE_GB:.4f} GB")
    print("=" * 70)
    
    if total_size <= max_size_bytes:
        available_space = max_size_bytes - total_size
        print(f"✓ PASS: Upload allowed!")
        print(f"  Available space after upload: {available_space / (1024 ** 3):.4f} GB")
        print("=" * 70 + "\n")
        return True
    else:
        excess = total_size - max_size_bytes
        print(f"✗ FAIL: Upload would exceed 10GB limit by {excess / (1024 ** 3):.4f} GB")
        print(f"  Please remove some files or delete existing files from the bucket.")
        print("=" * 70 + "\n")
        return False

def create_bucket_if_not_exists():
    """Create bucket if it doesn't exist"""
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket '{BUCKET_NAME}' already exists.\n")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                s3.create_bucket(Bucket=BUCKET_NAME)
                print(f"Bucket '{BUCKET_NAME}' created successfully.\n")
                return True
            except ClientError as create_error:
                print(f"Failed to create bucket: {create_error}")
                return False
        else:
            print(f"Error checking bucket: {e}")
            return False

def upload_files(files_to_upload):
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
    
    if not files_to_upload:
        print("No files found to upload.")
        return uploaded_files
    
    print(f"Found {len(files_to_upload)} file(s) to upload.\n")
    
    for item_name, item_path, file_size in files_to_upload:
        print(f"Uploading {item_name} ({file_size / (1024 ** 2):.2f} MB)...")
        
        total_bytes = file_size
        bytes_transferred = 0
        start_time = time.time()
        last_print_time = start_time
        
        try:
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
                ExpiresIn=expiration
            )
            presigned_urls.append((file_name, url))
        except ClientError as e:
            print(f"Error generating presigned URL for {file_name}: {e}")
    return presigned_urls

# Main execution
if __name__ == "__main__":
    print("=" * 70)
    print("Cloudflare R2 Storage Uploader (Free Tier - 10GB Limit)")
    print("=" * 70)
    print(f"Folder: {FOLDER_PATH}")
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Endpoint: https://{ACCOUNT_ID}.r2.cloudflarestorage.com")
    print("=" * 70 + "\n")
    
    # Create bucket if needed
    if not create_bucket_if_not_exists():
        print("✗ Cannot proceed without a valid bucket.")
        exit(1)
    
    # Get existing bucket size
    print("Checking existing files in bucket...")
    existing_size, existing_file_count = get_bucket_size()
    print(f"Found {existing_file_count} existing file(s) in bucket.\n")
    
    # Get local files to upload
    print("Scanning local files...")
    new_files_size, files_to_upload = get_local_files_size(FOLDER_PATH)
    
    if not files_to_upload:
        print("✗ No files found in the specified folder.")
        exit(0)
    
    print(f"Found {len(files_to_upload)} file(s) to upload.\n")
    
    # Check if upload would exceed 10GB limit
    if not check_size_limit(existing_size, new_files_size):
        print("✗ Upload cancelled: Would exceed 10GB free tier limit.")
        print("   Please delete some files from the bucket or reduce upload size.")
        exit(1)
    
    # Proceed with upload
    uploaded_files = upload_files(files_to_upload)
    
    if uploaded_files:
        print("\n" + "=" * 70)
        print(f"✓ Successfully uploaded {len(uploaded_files)} file(s)!")
        print("=" * 70 + "\n")
        
        # Show final bucket size
        final_size, final_count = get_bucket_size()
        print(f"Final bucket size: {final_size / (1024 ** 3):.4f} GB ({final_count} files)")
        print(f"Remaining space: {(MAX_TOTAL_SIZE_GB * 1024 ** 3 - final_size) / (1024 ** 3):.4f} GB\n")
        
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
