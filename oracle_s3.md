# OCI Object Storage with S3-Compatible API

A complete guide for using Oracle Cloud Infrastructure (OCI) Object Storage with S3-compatible tools via the OCI CLI.

## Overview

Oracle Cloud Infrastructure provides an S3-compatible API for its Object Storage service, allowing you to use standard S3 tools like boto3 with OCI buckets. This guide covers the entire setup process using only the OCI CLI.

## Prerequisites

- **OCI Account**: Active Oracle Cloud account
- **OCI CLI**: Installed and configured
    - Pre-configured in OCI Cloud Shell
    - For local setup: [OCI CLI Installation Guide](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)


## OCI to S3 Terminology Mapping

| S3 (AWS) Term | OCI (Oracle) Term | How to Find It |
| :-- | :-- | :-- |
| Bucket Name | Bucket Name | You create this (must be unique in namespace) |
| AWS Access Key ID | Customer Secret Key (Access Key) | The `id` in the generated output |
| AWS Secret Key | Customer Secret Key (Secret Key) | The `key` in the generated output |
| AWS Region | OCI Region | e.g., `us-ashburn-1`, `eu-frankfurt-1` |
| S3 Endpoint | S3-Compatible Endpoint | `https://<namespace>.compat.objectstorage.<region>.oraclecloud.com` |

## Setup Steps

### Step 1: Gather Core Information

#### A. Find Your Tenancy (Root Compartment) OCID

**In OCI Cloud Shell:**

```bash
curl -H "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v1/instance/compartmentId
```

**On Local CLI:**

```bash
cat ~/.oci/config | grep tenancy
```


#### B. Find Your User OCID

```bash
oci session user get --query "data.id" --raw-output
```


#### C. Find Your Object Storage Namespace

```bash
oci os ns get --query "data" --raw-output
```


### Step 2: Create Your Bucket

Replace `<your_tenancy_ocid>` and `<your_unique_bucket_name>` with your values:

```bash
oci os bucket create \
    --compartment-id <your_tenancy_ocid> \
    --name <your_unique_bucket_name>
```

**Example:**

```bash
oci os bucket create \
    --compartment-id ocid1.tenancy.oc1..aaaa... \
    --name my-s3-bucket
```


### Step 3: Generate S3-Compatible Keys

Replace `<your_user_ocid>` and `<key_display_name>`:

```bash
oci iam customer-secret-key create \
    --user-id <your_user_ocid> \
    --display-name <key_display_name>
```

**Example:**

```bash
oci iam customer-secret-key create \
    --user-id ocid1.user.oc1..aaaa... \
    --display-name "my-s3-app-key"
```


#### ⚠️ IMPORTANT: Save Your Keys

The output contains your credentials (shown only once):

```json
{
  "data": {
    "display-name": "my-s3-app-key",
    "id": "aaaabbbbccccdddd1111",            // S3 ACCESS KEY ID
    "key": "A1b2C/d3E+f4G/h5iJk6L+mN==",    // S3 SECRET ACCESS KEY
    "lifecycle-state": "ACTIVE",
    "time-created": "2025-10-23T08:15:00.123+00:00",
    "user-id": "ocid1.user.oc1..aaaa..."
  }
}
```

**Save the `id` and `key` values immediately in a secure password manager.**

### Step 4: Configure Permissions (IAM Policy)

For non-admin users, create a group and policy:

#### Create a Group

```bash
oci iam group create --name S3-Users --description "Users who need S3 access"
```


#### Add User to Group

```bash
oci iam group add-user \
    --user-id <your_user_ocid> \
    --group-id <group_id_from_previous_step>
```


#### Create Policy

```bash
oci iam policy create \
    --compartment-id <your_tenancy_ocid> \
    --name S3-User-Policy \
    --description "Allow S3-Users to manage all buckets and objects" \
    --statements '["Allow group S3-Users to manage object-family in tenancy"]'
```


## Usage with Boto3

### Required Information

1. **Access Key ID**: The `id` from Step 3
2. **Secret Access Key**: The `key` from Step 3
3. **Bucket Name**: From Step 2
4. **Region**: Your OCI region (e.g., `us-ashburn-1`)
5. **Namespace**: From Step 1C

### Endpoint URL Format

```
https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
```


### Python Upload Script

```python
import os
import time
from datetime import timedelta
from urllib.parse import quote
import boto3
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig

# Configure checksum settings
os.environ['AWS_REQUEST_CHECKSUM_CALCULATION'] = 'when_required'
os.environ['AWS_RESPONSE_CHECKSUM_VALIDATION'] = 'when_required'

# --- CONFIGURATION: Fill in your values ---
namespace = 'YOUR_NAMESPACE'              # From Step 1C
region = 'ap-hyderabad-1'                 # Your OCI region
aws_access_key_id = 'YOUR_ACCESS_KEY'     # From Step 3 ("id")
aws_secret_access_key = 'YOUR_SECRET'     # From Step 3 ("key")
bucket_name = 'YOUR_BUCKET_NAME'          # From Step 2
folder_path = '/path/to/your/files'       # Folder to upload
# ------------------------------------------

s3 = boto3.client(
    service_name='s3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    endpoint_url=f'https://{namespace}.compat.objectstorage.{region}.oraclecloud.com',
    region_name=region
)

# Global progress tracking
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
        encoded_name = quote(file_name, safe='')
        url = f"https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket_name}/o/{encoded_name}"
        public_urls.append((file_name, url))
    return public_urls

def generate_presigned_urls(file_names, expiration=604800):
    """Generate presigned URLs for 7-day access (604800 seconds)"""
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
```


## URL Access Methods

### Public URLs (Permanent)

- **Format**: `https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket}/o/{object}`
- **Requirement**: Bucket must be set to public
- **Duration**: Permanent


### Presigned URLs (Temporary)

- Generated via boto3's `generate_presigned_url()` method
- **Duration**: Configurable (default: 7 days)
- **Advantage**: Works with private buckets


## Notes

- Administrator users typically have default permissions; non-admin users need explicit IAM policies
- Customer Secret Keys are shown only once during creation
- Transfer speeds depend on network connectivity and OCI region proximity
- Multipart uploads are automatically used for files larger than 8MB


## License

This guide is provided as-is for educational and reference purposes.

***

Would you like me to add installation instructions for boto3 or a troubleshooting section?

