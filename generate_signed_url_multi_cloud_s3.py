import boto3
from botocore.exceptions import ClientError
from botocore.client import Config

# Cloud configurations
CLOUDS = {
    'ImpossibleCloud': {
        'client': None,
        'config': {
            'service_name': 's3',
            'aws_access_key_id': 'id',
            'aws_secret_access_key': 'id',
            'endpoint_url': 'https://eu-central-2.storage.impossibleapi.net',
            'region_name': 'eu-central-2'
        },
        'bucket_name': 'bucket'
    },
    'Wasabi': {
        'client': None,
        'config': {
            'service_name': 's3',
            'aws_access_key_id': 'id',
            'aws_secret_access_key': 'id',
            'endpoint_url': 'https://s3.ap-northeast-1.wasabisys.com',
            'region_name': 'ap-northeast-1'
        },
        'bucket_name': 'bucket'
    },
    'CloudflareR2': {
        'client': None,
        'config': {
            'service_name': 's3',
            'aws_access_key_id': 'id',  # R2 API Access Key ID
            'aws_secret_access_key': 'id',  # R2 API Secret Access Key
            'endpoint_url': 'https://account_id.r2.cloudflarestorage.com',  # Replace 'id' with your Account ID
            'region_name': 'auto',
            'config': Config(signature_version='s3v4')
        },
        'bucket_name': 'bucket'
    }
}

# URL expiration time (7 days = 604800 seconds)
URL_EXPIRATION = 604800

def initialize_clients():
    """Initialize S3 clients for all clouds"""
    print("Initializing cloud clients...")
    for cloud_name, cloud_info in CLOUDS.items():
        try:
            # Special handling for Cloudflare R2
            if cloud_name == 'CloudflareR2':
                config = cloud_info['config'].pop('config', None)
                cloud_info['client'] = boto3.client(**cloud_info['config'], config=config)
            else:
                cloud_info['client'] = boto3.client(**cloud_info['config'])
            print(f"  ✓ {cloud_name} client initialized")
        except Exception as e:
            print(f"  ✗ Failed to initialize {cloud_name} client: {e}")
            cloud_info['client'] = None
    print()

def list_files_in_bucket(cloud_name):
    """List all files in the bucket"""
    cloud_info = CLOUDS[cloud_name]
    s3_client = cloud_info['client']
    bucket_name = cloud_info['bucket_name']
    
    if not s3_client:
        print(f"  [{cloud_name}] ✗ Client not initialized")
        return []
    
    try:
        # Handle pagination for buckets with many files
        files = []
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)
        
        for page in pages:
            if 'Contents' in page:
                files.extend([obj['Key'] for obj in page['Contents']])
        
        if not files:
            print(f"  [{cloud_name}] No files found in bucket '{bucket_name}'")
            return []
        
        print(f"  [{cloud_name}] Found {len(files)} file(s) in bucket '{bucket_name}'")
        return files
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchBucket':
            print(f"  [{cloud_name}] ✗ Bucket '{bucket_name}' does not exist")
        else:
            print(f"  [{cloud_name}] ✗ Error listing files: {e}")
        return []

def generate_presigned_urls(cloud_name, file_names):
    """Generate presigned URLs for all files"""
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
                ExpiresIn=URL_EXPIRATION
            )
            presigned_urls.append((file_name, url))
            print(f"  [{cloud_name}] ✓ Generated URL for: {file_name}")
        except ClientError as e:
            print(f"  [{cloud_name}] ✗ Error generating URL for {file_name}: {e}")
    
    return presigned_urls

def print_urls(all_urls):
    """Print all presigned URLs in an organized format"""
    print("\n" + "=" * 70)
    print("PRESIGNED URLs (Valid for 7 days)")
    print("=" * 70)
    
    for cloud_name, urls in all_urls.items():
        if urls:
            cloud_info = CLOUDS[cloud_name]
            endpoint = cloud_info['config']['endpoint_url']
            print(f"\n{cloud_name}:")
            print(f"Endpoint: {endpoint}")
            print(f"Bucket: {cloud_info['bucket_name']}")
            print("-" * 70)
            
            for file_name, url in urls:
                print(f"\nFile: {file_name}")
                print(f"URL: {url}")
            
            print()
    
    print("=" * 70)
    print(f"NOTE: These URLs will expire in 7 days ({URL_EXPIRATION} seconds)")
    print("Re-run this script to generate new URLs after expiration.")
    print("=" * 70)

def save_urls_to_file(all_urls, filename='presigned_urls.txt'):
    """Save all URLs to a text file"""
    try:
        with open(filename, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("PRESIGNED URLs (Valid for 7 days)\n")
            f.write("=" * 70 + "\n\n")
            
            for cloud_name, urls in all_urls.items():
                if urls:
                    cloud_info = CLOUDS[cloud_name]
                    endpoint = cloud_info['config']['endpoint_url']
                    f.write(f"{cloud_name}:\n")
                    f.write(f"Endpoint: {endpoint}\n")
                    f.write(f"Bucket: {cloud_info['bucket_name']}\n")
                    f.write("-" * 70 + "\n\n")
                    
                    for file_name, url in urls:
                        f.write(f"File: {file_name}\n")
                        f.write(f"URL: {url}\n\n")
                    
                    f.write("\n")
            
            f.write("=" * 70 + "\n")
            f.write(f"NOTE: These URLs will expire in 7 days ({URL_EXPIRATION} seconds)\n")
            f.write("=" * 70 + "\n")
        
        print(f"\n✓ URLs saved to '{filename}'")
        return True
    except Exception as e:
        print(f"\n✗ Failed to save URLs to file: {e}")
        return False

# Main execution
if __name__ == "__main__":
    print("=" * 70)
    print("PRESIGNED URL GENERATOR")
    print("Generate 7-Day Access URLs for Multi-Cloud S3 Storage")
    print("ImpossibleCloud + Wasabi + Cloudflare R2")
    print("=" * 70)
    print()
    
    # Initialize clients
    initialize_clients()
    
    # Get files from all clouds and generate URLs
    print("Listing files and generating presigned URLs...")
    print()
    
    all_urls = {}
    
    for cloud_name in CLOUDS.keys():
        files = list_files_in_bucket(cloud_name)
        if files:
            print(f"\nGenerating URLs for {cloud_name}...")
            urls = generate_presigned_urls(cloud_name, files)
            all_urls[cloud_name] = urls
        else:
            all_urls[cloud_name] = []
        print()
    
    # Print all URLs
    print_urls(all_urls)
    
    # Save to file
    save_urls_to_file(all_urls)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_urls = 0
    for cloud_name, urls in all_urls.items():
        url_count = len(urls)
        total_urls += url_count
        print(f"{cloud_name}: {url_count} URL(s) generated")
    print("-" * 70)
    print(f"Total: {total_urls} presigned URL(s) generated across all clouds")
    print("=" * 70)
