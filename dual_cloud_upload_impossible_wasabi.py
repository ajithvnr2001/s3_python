# multi s3 upload currently impossible+ wasabi
import os
import time
from datetime import timedelta
import boto3
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig

# Cloud configurations
CLOUDS = {
    'ImpossibleCloud': {
        'client': None,
        'config': {
            'service_name': 's3',
            'aws_access_key_id': 'key',
            'aws_secret_access_key': 'sec_key',
            'endpoint_url': 'https://eu-central-2.storage.impossibleapi.net',
            'region_name': 'eu-central-2'
        },
        'bucket_name': 'bucket'
    },
    'Wasabi': {
        'client': None,
        'config': {
            'service_name': 's3',
            'aws_access_key_id': 'key',
            'aws_secret_access_key': 'sec_key',
            'endpoint_url': 'https://s3.ap-northeast-1.wasabisys.com',
            'region_name': 'ap-northeast-1'
        },
        'bucket_name': 'bucket'
    }
}

# Set the folder path
folder_path = '/content/3'

# Transfer configuration
transfer_config = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,  # 8MB
    max_concurrency=10,
    multipart_chunksize=8 * 1024 * 1024,
    use_threads=True
)

class ProgressTracker:
    """Track upload progress for a single file"""
    def __init__(self, cloud_name, file_name, total_bytes):
        self.cloud_name = cloud_name
        self.file_name = file_name
        self.total_bytes = total_bytes
        self.bytes_transferred = 0
        self.start_time = time.time()
        self.last_print_time = self.start_time
    
    def __call__(self, new_bytes):
        """Callback function for upload progress"""
        self.bytes_transferred += new_bytes
        
        # Print progress every second
        current_time = time.time()
        if current_time - self.last_print_time >= 1.0:
            elapsed_time = max(current_time - self.start_time, 0.001)
            speed = (self.bytes_transferred / (1024 ** 2)) / elapsed_time
            remaining_bytes = self.total_bytes - self.bytes_transferred
            
            if self.bytes_transferred > 0:
                estimated_seconds = remaining_bytes / (self.bytes_transferred / elapsed_time)
                estimated_remaining_time = str(timedelta(seconds=int(estimated_seconds)))
            else:
                estimated_remaining_time = "Unknown"
            
            percentage = (self.bytes_transferred / self.total_bytes) * 100
            
            print(f'\r  [{self.cloud_name}] {percentage:.1f}% | '
                  f'{self.bytes_transferred / (1024 ** 3):.2f}/{self.total_bytes / (1024 ** 3):.2f} GB | '
                  f'Speed: {speed:.2f} MB/s | '
                  f'ETA: {estimated_remaining_time}', end='', flush=True)
            
            self.last_print_time = current_time

def initialize_clients():
    """Initialize S3 clients for both clouds"""
    for cloud_name, cloud_info in CLOUDS.items():
        try:
            cloud_info['client'] = boto3.client(**cloud_info['config'])
            print(f"✓ Initialized {cloud_name} client")
        except Exception as e:
            print(f"✗ Failed to initialize {cloud_name} client: {e}")
            cloud_info['client'] = None

def create_bucket_if_not_exists(cloud_name):
    """Create bucket if it doesn't exist"""
    cloud_info = CLOUDS[cloud_name]
    s3_client = cloud_info['client']
    bucket_name = cloud_info['bucket_name']
    
    if not s3_client:
        return False
    
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"  [{cloud_name}] Bucket '{bucket_name}' already exists")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                s3_client.create_bucket(Bucket=bucket_name)
                print(f"  [{cloud_name}] Bucket '{bucket_name}' created successfully")
                return True
            except ClientError as create_error:
                print(f"  [{cloud_name}] Failed to create bucket: {create_error}")
                return False
        else:
            print(f"  [{cloud_name}] Error checking bucket: {e}")
            return False

def upload_file_to_cloud(cloud_name, file_name, file_path, file_size):
    """Upload a single file to a specific cloud"""
    cloud_info = CLOUDS[cloud_name]
    s3_client = cloud_info['client']
    bucket_name = cloud_info['bucket_name']
    
    if not s3_client:
        print(f"  [{cloud_name}] ✗ Client not initialized")
        return False
    
    try:
        progress_tracker = ProgressTracker(cloud_name, file_name, file_size)
        
        s3_client.upload_file(
            file_path,
            bucket_name,
            file_name,
            Config=transfer_config,
            Callback=progress_tracker
        )
        print(f'\n  [{cloud_name}] ✓ Successfully uploaded {file_name}')
        return True
    except ClientError as e:
        print(f"\n  [{cloud_name}] ✗ Failed to upload {file_name}: {e}")
        return False

def upload_files():
    """Upload all files from the specified folder to both clouds"""
    results = {cloud: [] for cloud in CLOUDS.keys()}
    
    # Get list of files to upload
    if not os.path.exists(folder_path):
        print(f"\n✗ Error: Folder '{folder_path}' does not exist!")
        return results
    
    files_to_upload = []
    for item_name in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item_name)
        if os.path.isfile(item_path):
            files_to_upload.append((item_name, item_path))
    
    if not files_to_upload:
        print("\n✗ No files found to upload.")
        return results
    
    print(f"\nFound {len(files_to_upload)} file(s) to upload.\n")
    
    for item_name, item_path in files_to_upload:
        file_size = os.path.getsize(item_path)
        print(f"{'=' * 70}")
        print(f"Uploading: {item_name} ({file_size / (1024 ** 3):.2f} GB)")
        print(f"{'=' * 70}")
        
        # Upload to both clouds
        for cloud_name in CLOUDS.keys():
            success = upload_file_to_cloud(cloud_name, item_name, item_path, file_size)
            if success:
                results[cloud_name].append(item_name)
        
        print()
    
    return results

def generate_presigned_urls(cloud_name, file_names, expiration=604800):
    """Generate presigned URLs for 7-day access (604800 seconds = 7 days)"""
    cloud_info = CLOUDS[cloud_name]
    s3_client = cloud_info['client']
    bucket_name = cloud_info['bucket_name']
    
    if not s3_client:
        return []
    
    presigned_urls = []
    for file_name in file_names:
        try:
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_name},
                ExpiresIn=expiration
            )
            presigned_urls.append((file_name, url))
        except ClientError as e:
            print(f"  [{cloud_name}] Error generating presigned URL for {file_name}: {e}")
    
    return presigned_urls

def print_summary(results):
    """Print upload summary and presigned URLs"""
    print("\n" + "=" * 70)
    print("UPLOAD SUMMARY")
    print("=" * 70)
    
    for cloud_name, uploaded_files in results.items():
        cloud_info = CLOUDS[cloud_name]
        print(f"\n{cloud_name}:")
        print(f"  Endpoint: {cloud_info['config']['endpoint_url']}")
        print(f"  Bucket: {cloud_info['bucket_name']}")
        print(f"  Files uploaded: {len(uploaded_files)}")
        
        if uploaded_files:
            print(f"  ✓ Successfully uploaded {len(uploaded_files)} file(s)")
        else:
            print(f"  ✗ No files uploaded")
    
    print("\n" + "=" * 70)
    print("PRESIGNED URLs (Valid for 7 days)")
    print("=" * 70)
    
    for cloud_name, uploaded_files in results.items():
        if uploaded_files:
            print(f"\n{cloud_name}:")
            print("-" * 70)
            presigned_urls = generate_presigned_urls(cloud_name, uploaded_files)
            for file_name, url in presigned_urls:
                print(f"\n{file_name}:")
                print(f"{url}")
            print()
    
    print("=" * 70)
    print("NOTE: These URLs will expire in 7 days.")
    print("Re-run the script to generate new URLs if needed.")
    print("=" * 70)

# Main execution
if __name__ == "__main__":
    print("=" * 70)
    print("DUAL CLOUD STORAGE UPLOADER")
    print("ImpossibleCloud + Wasabi S3")
    print("=" * 70)
    print(f"Folder: {folder_path}")
    print("=" * 70 + "\n")
    
    print("Initializing cloud clients...")
    initialize_clients()
    print()
    
    print("Checking/Creating buckets...")
    for cloud_name in CLOUDS.keys():
        create_bucket_if_not_exists(cloud_name)
    print()
    
    results = upload_files()
    print_summary(results)
