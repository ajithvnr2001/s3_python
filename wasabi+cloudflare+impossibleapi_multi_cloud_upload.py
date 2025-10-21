# Multi-cloud storage uploader with size limit checks
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

# Cloudflare R2 Configuration
R2_CONFIG = {
    'name': 'Cloudflare R2',
    'account_id': 'id',           # Your Cloudflare Account ID
    'access_key_id': 'id',        # R2 API Access Key ID
    'secret_access_key': 'id',    # R2 API Secret Access Key
    'bucket_name': 'bucket',       # Your R2 bucket name
    'max_size_gb': 9.5,            # Maximum total size in GB (with safety margin)
    'client': None,
    'enabled': True                # Set to False to disable R2 uploads
}

# ImpossibleCloud Configuration
IMPOSSIBLE_CONFIG = {
    'name': 'ImpossibleCloud',
    'access_key_id': 'id',
    'secret_access_key': 'id',
    'endpoint_url': 'https://eu-central-2.storage.impossibleapi.net',
    'region_name': 'eu-central-2',
    'bucket_name': 'bucket',
    'max_size_gb': None,           # Set to None for no limit, or specify GB limit
    'client': None,
    'enabled': True                # Set to False to disable ImpossibleCloud uploads
}

# Wasabi Configuration
WASABI_CONFIG = {
    'name': 'Wasabi',
    'access_key_id': 'id',
    'secret_access_key': 'id',
    'endpoint_url': 'https://s3.ap-northeast-1.wasabisys.com',
    'region_name': 'ap-northeast-1',
    'bucket_name': 'thisismybuck',
    'max_size_gb': None,           # Set to None for no limit, or specify GB limit
    'client': None,
    'enabled': True                # Set to False to disable Wasabi uploads
}

# Folder to upload from
FOLDER_PATH = '/content/3'

# Transfer configuration for multipart uploads
TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,  # 8MB
    max_concurrency=10,
    multipart_chunksize=8 * 1024 * 1024,
    use_threads=True
)

# ============================================================================
# PROGRESS TRACKING CLASS
# ============================================================================

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

# ============================================================================
# CLOUD CLIENT INITIALIZATION
# ============================================================================

def initialize_r2_client():
    """Initialize Cloudflare R2 client"""
    if not R2_CONFIG['enabled']:
        print(f"  [{R2_CONFIG['name']}] Disabled - skipping")
        return False
    
    try:
        R2_CONFIG['client'] = boto3.client(
            service_name='s3',
            endpoint_url=f"https://{R2_CONFIG['account_id']}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_CONFIG['access_key_id'],
            aws_secret_access_key=R2_CONFIG['secret_access_key'],
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        print(f"  ✓ Initialized {R2_CONFIG['name']} client")
        return True
    except Exception as e:
        print(f"  ✗ Failed to initialize {R2_CONFIG['name']} client: {e}")
        R2_CONFIG['client'] = None
        return False

def initialize_s3_client(config):
    """Initialize S3-compatible client (ImpossibleCloud/Wasabi)"""
    if not config['enabled']:
        print(f"  [{config['name']}] Disabled - skipping")
        return False
    
    try:
        config['client'] = boto3.client(
            service_name='s3',
            aws_access_key_id=config['access_key_id'],
            aws_secret_access_key=config['secret_access_key'],
            endpoint_url=config['endpoint_url'],
            region_name=config['region_name']
        )
        print(f"  ✓ Initialized {config['name']} client")
        return True
    except Exception as e:
        print(f"  ✗ Failed to initialize {config['name']} client: {e}")
        config['client'] = None
        return False

def initialize_all_clients():
    """Initialize all cloud clients"""
    print("Initializing cloud clients...")
    initialize_r2_client()
    initialize_s3_client(IMPOSSIBLE_CONFIG)
    initialize_s3_client(WASABI_CONFIG)
    print()

# ============================================================================
# SIZE CHECKING FUNCTIONS
# ============================================================================

def get_bucket_size(config):
    """Calculate total size of all files in a bucket"""
    if not config['client']:
        return 0, 0
    
    total_size = 0
    file_count = 0
    
    try:
        paginator = config['client'].get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=config['bucket_name'])
        
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
            print(f"  [{config['name']}] Error getting bucket size: {e}")
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

def check_size_limit(config, existing_size, new_files_size):
    """Check if total size would exceed the configured limit"""
    if config['max_size_gb'] is None:
        # No limit configured
        return True, "No limit"
    
    max_size_bytes = config['max_size_gb'] * 1024 ** 3
    total_size = existing_size + new_files_size
    
    if total_size <= max_size_bytes:
        available_space = max_size_bytes - total_size
        return True, f"Available: {available_space / (1024 ** 3):.4f} GB"
    else:
        excess = total_size - max_size_bytes
        return False, f"Exceeds by: {excess / (1024 ** 3):.4f} GB"

def check_all_size_limits(configs, new_files_size):
    """Check size limits for all enabled cloud providers"""
    print("=" * 70)
    print("SIZE LIMIT CHECKS")
    print("=" * 70)
    
    all_passed = True
    results = {}
    
    for config in configs:
        if not config['enabled'] or not config['client']:
            continue
        
        print(f"\n[{config['name']}]")
        print("-" * 70)
        
        existing_size, existing_count = get_bucket_size(config)
        
        if config['max_size_gb'] is not None:
            total_size = existing_size + new_files_size
            max_size_bytes = config['max_size_gb'] * 1024 ** 3
            
            print(f"  Existing files: {existing_size / (1024 ** 3):.4f} GB ({existing_count} files)")
            print(f"  New files:      {new_files_size / (1024 ** 3):.4f} GB")
            print(f"  Total would be: {total_size / (1024 ** 3):.4f} GB")
            print(f"  Maximum limit:  {config['max_size_gb']:.4f} GB")
            
            passed, message = check_size_limit(config, existing_size, new_files_size)
            
            if passed:
                print(f"  ✓ PASS: {message}")
                results[config['name']] = True
            else:
                print(f"  ✗ FAIL: {message}")
                results[config['name']] = False
                all_passed = False
        else:
            print(f"  Existing files: {existing_size / (1024 ** 3):.4f} GB ({existing_count} files)")
            print(f"  New files:      {new_files_size / (1024 ** 3):.4f} GB")
            print(f"  ✓ PASS: No size limit configured")
            results[config['name']] = True
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✓ ALL SIZE CHECKS PASSED - Upload can proceed")
    else:
        print("✗ SOME SIZE CHECKS FAILED - Upload will be skipped for failed providers")
    print("=" * 70 + "\n")
    
    return results

# ============================================================================
# BUCKET MANAGEMENT
# ============================================================================

def create_bucket_if_not_exists(config):
    """Create bucket if it doesn't exist"""
    if not config['client']:
        return False
    
    try:
        config['client'].head_bucket(Bucket=config['bucket_name'])
        print(f"  [{config['name']}] Bucket '{config['bucket_name']}' exists")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                config['client'].create_bucket(Bucket=config['bucket_name'])
                print(f"  [{config['name']}] Bucket '{config['bucket_name']}' created")
                return True
            except ClientError as create_error:
                print(f"  [{config['name']}] Failed to create bucket: {create_error}")
                return False
        else:
            print(f"  [{config['name']}] Error checking bucket: {e}")
            return False

def check_all_buckets():
    """Check/create buckets for all enabled providers"""
    print("Checking/Creating buckets...")
    configs = [R2_CONFIG, IMPOSSIBLE_CONFIG, WASABI_CONFIG]
    for config in configs:
        if config['enabled'] and config['client']:
            create_bucket_if_not_exists(config)
    print()

# ============================================================================
# FILE UPLOAD FUNCTIONS
# ============================================================================

def upload_file_to_cloud(config, file_name, file_path, file_size, size_check_passed):
    """Upload a single file to a specific cloud"""
    if not config['client']:
        print(f"  [{config['name']}] ✗ Client not initialized")
        return False
    
    if not size_check_passed:
        print(f"  [{config['name']}] ✗ Skipped (size limit exceeded)")
        return False
    
    try:
        progress_tracker = ProgressTracker(config['name'], file_name, file_size)
        
        config['client'].upload_file(
            file_path,
            config['bucket_name'],
            file_name,
            Config=TRANSFER_CONFIG,
            Callback=progress_tracker
        )
        print(f'\n  [{config["name"]}] ✓ Successfully uploaded {file_name}')
        return True
    except ClientError as e:
        print(f"\n  [{config['name']}] ✗ Failed to upload {file_name}: {e}")
        return False

def upload_all_files(files_to_upload, size_check_results):
    """Upload all files to all enabled cloud providers"""
    results = {
        R2_CONFIG['name']: [],
        IMPOSSIBLE_CONFIG['name']: [],
        WASABI_CONFIG['name']: []
    }
    
    configs = [R2_CONFIG, IMPOSSIBLE_CONFIG, WASABI_CONFIG]
    
    for item_name, item_path, file_size in files_to_upload:
        print(f"{'=' * 70}")
        print(f"Uploading: {item_name} ({file_size / (1024 ** 3):.2f} GB)")
        print(f"{'=' * 70}")
        
        for config in configs:
            if not config['enabled'] or not config['client']:
                continue
            
            size_passed = size_check_results.get(config['name'], False)
            success = upload_file_to_cloud(config, item_name, item_path, file_size, size_passed)
            
            if success:
                results[config['name']].append(item_name)
        
        print()
    
    return results

# ============================================================================
# PRESIGNED URL GENERATION
# ============================================================================

def generate_presigned_urls(config, file_names, expiration=604800):
    """Generate presigned URLs for 7-day access"""
    if not config['client']:
        return []
    
    presigned_urls = []
    for file_name in file_names:
        try:
            url = config['client'].generate_presigned_url(
                'get_object',
                Params={'Bucket': config['bucket_name'], 'Key': file_name},
                ExpiresIn=expiration
            )
            presigned_urls.append((file_name, url))
        except ClientError as e:
            print(f"  [{config['name']}] Error generating URL for {file_name}: {e}")
    
    return presigned_urls

# ============================================================================
# SUMMARY AND REPORTING
# ============================================================================

def print_summary(results):
    """Print upload summary and presigned URLs"""
    print("\n" + "=" * 70)
    print("UPLOAD SUMMARY")
    print("=" * 70)
    
    configs = [R2_CONFIG, IMPOSSIBLE_CONFIG, WASABI_CONFIG]
    
    for config in configs:
        if not config['enabled']:
            continue
        
        uploaded_files = results.get(config['name'], [])
        
        print(f"\n[{config['name']}]")
        endpoint = config.get('endpoint_url') or f"https://{config.get('account_id')}.r2.cloudflarestorage.com"
        print(f"  Endpoint: {endpoint}")
        print(f"  Bucket: {config['bucket_name']}")
        print(f"  Files uploaded: {len(uploaded_files)}")
        
        if uploaded_files:
            print(f"  ✓ Successfully uploaded {len(uploaded_files)} file(s)")
            
            # Show final bucket size
            final_size, final_count = get_bucket_size(config)
            print(f"  Final bucket size: {final_size / (1024 ** 3):.4f} GB ({final_count} files)")
            
            if config['max_size_gb'] is not None:
                remaining = (config['max_size_gb'] * 1024 ** 3) - final_size
                print(f"  Remaining space: {remaining / (1024 ** 3):.4f} GB")
        else:
            print(f"  ✗ No files uploaded")
    
    print("\n" + "=" * 70)
    print("PRESIGNED URLs (Valid for 7 days)")
    print("=" * 70)
    
    for config in configs:
        if not config['enabled']:
            continue
        
        uploaded_files = results.get(config['name'], [])
        
        if uploaded_files:
            print(f"\n[{config['name']}]")
            print("-" * 70)
            presigned_urls = generate_presigned_urls(config, uploaded_files)
            for file_name, url in presigned_urls:
                print(f"\n{file_name}:")
                print(f"{url}")
            print()
    
    print("=" * 70)
    print("NOTE: These URLs will expire in 7 days.")
    print("Re-run the script to generate new URLs if needed.")
    print("=" * 70)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MULTI-CLOUD STORAGE UPLOADER")
    print("Cloudflare R2 + ImpossibleCloud + Wasabi")
    print("=" * 70)
    print(f"Folder: {FOLDER_PATH}")
    print("=" * 70 + "\n")
    
    # Initialize all cloud clients
    initialize_all_clients()
    
    # Check/create buckets
    check_all_buckets()
    
    # Scan local files
    print("Scanning local files...")
    new_files_size, files_to_upload = get_local_files_size(FOLDER_PATH)
    
    if not files_to_upload:
        print("✗ No files found in the specified folder.")
        exit(0)
    
    print(f"Found {len(files_to_upload)} file(s) to upload")
    print(f"Total size: {new_files_size / (1024 ** 3):.4f} GB\n")
    
    # Check size limits for all providers
    configs = [R2_CONFIG, IMPOSSIBLE_CONFIG, WASABI_CONFIG]
    size_check_results = check_all_size_limits(configs, new_files_size)
    
    # Check if at least one provider can accept the upload
    if not any(size_check_results.values()):
        print("✗ Upload cancelled: All providers failed size checks.")
        exit(1)
    
    # Upload files
    results = upload_all_files(files_to_upload, size_check_results)
    
    # Print summary
    print_summary(results)
