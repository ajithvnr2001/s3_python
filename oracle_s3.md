Using OCI Object Storage with S3-Compatible APIs via the CLI

Oracle Cloud Infrastructure (OCI) provides an S3-compatible API for its Object Storage service. This allows you to use S3-compatible tools, like boto3, with your OCI buckets.

This guide covers the complete end-to-end process using the OCI CLI.

Prerequisites

OCI Account: You must have an Oracle Cloud account.

OCI CLI: The OCI Command Line Interface must be installed and configured.

If you are using the OCI Cloud Shell, the CLI is pre-configured.

For a local setup, see the OCI CLI Installation Guide.

OCI to S3: Understanding the "Where to Find What"

Before you begin, it's crucial to understand how OCI's terms map to standard S3 terms:

S3 (AWS) Term

OCI (Oracle) Term

How to Find It (via OCI CLI)

Bucket Name

Bucket Name

You create this. Must be unique in your namespace.

AWS Access Key ID

Customer Secret Key (Access Key)

You generate this. It's the id in the output.

AWS Secret Key

Customer Secret Key (Secret Key)

You generate this. It's the key in the output.

AWS Region

OCI Region

e.g., us-ashburn-1, eu-frankfurt-1

S3 Endpoint

S3-Compatible Endpoint

https://<namespace>.compat.objectstorage.<region>.oraclecloud.com

You will need to find three key pieces of information:

Your Tenancy (Root Compartment) OCID: Where you'll create the bucket (for simplicity).

Your User OCID: The user who will "own" the S3 keys.

Your Object Storage Namespace: This is critical for the S3 endpoint URL.

Step 1: Find Your Core Information (Tenancy, User, Namespace)

Run these commands in your OCI CLI (Cloud Shell recommended) to gather the IDs you'll need.

A. Find Your Tenancy (Root Compartment) OCID

This is the OCID for your main root compartment (e.g., my-root-compartment (root)).

If in OCI Cloud Shell (Easiest Method):

curl -H "Authorization: Bearer Oracle" -L [http://169.254.169.254/opc/v1/instance/compartmentId](http://169.254.169.254/opc/v1/instance/compartmentId)


If on a Local CLI:

cat ~/.oci/config | grep tenancy


You will get a line like tenancy=ocid1.tenancy.oc1..aaaa.... Copy the OCID.

B. Find Your User OCID

This command gets the OCID of the currently authenticated user.

oci session user get --query "data.id" --raw-output


C. Find Your Object Storage Namespace

This is a unique string for your tenancy (e.g., my-namespace).

oci os ns get --query "data" --raw-output


Save these three values. You'll need them for the next steps and for your S3-compatible application.

Step 2: Create Your Bucket

Use the oci os bucket create command. For simplicity, we will create this in your root compartment (Tenancy).

Replace <your_tenancy_ocid> with the ID from Step 1A.

Replace <your_unique_bucket_name> with your desired bucket name (e.g., my-s3-bucket).

oci os bucket create \
    --compartment-id <your_tenancy_ocid> \
    --name <your_unique_bucket_name>


Example:

oci os bucket create \
    --compartment-id ocid1.tenancy.oc1..aaaa... \
    --name my-s3-bucket


If successful, you will see a JSON output confirming the bucket is created.

Step 3: Generate S3-Compatible Keys

Now, create the S3-compatible Access Key and Secret Key, which OCI calls a "Customer Secret Key".

Replace <your_user_ocid> with the ID from Step 1B.

Replace <key_display_name> with a memorable name for the key.

oci iam customer-secret-key create \
    --user-id <your_user_ocid> \
    --display-name <key_display_name>


Example:

oci iam customer-secret-key create \
    --user-id ocid1.user.oc1..aaaa... \
    --display-name "my-s3-app-key"


⚠️ IMPORTANT: SAVE YOUR KEYS

The CLI will output a JSON block. This is the only time you will ever see the secret key.

{
  "data": {
    "display-name": "my-s3-app-key",
    "id": "aaaabbbbccccdddd1111",            <-- THIS IS YOUR S3 ACCESS KEY ID
    "key": "A1b2C/d3E+f4G/h5iJk6L+mN==",  <-- THIS IS YOUR S3 SECRET ACCESS KEY
    "lifecycle-state": "ACTIVE",
    "time-created": "2025-10-23T08:15:00.123+00:00",
    "user-id": "ocid1.user.oc1..aaaa..."
  }
}


Save the id and key values in a secure password manager immediately.

Step 4: Providing Permissions (OCI IAM Policy)

By default, the new S3 keys can only do what the user they are tied to (the user from Step 1B) can do. For your S3 tool to read and write to buckets, that user must have Object Storage permissions.

If you are the tenancy administrator, you likely already have a policy like Allow group Administrators to manage all-resources in tenancy, which is why your bucket creation worked.

For a non-admin user, you must create a policy to grant them access. The best practice is to create a group, add the user to the group, and create a policy for that group.

Example: Granting a group access to all buckets in the tenancy

Create a Group:

oci iam group create --name S3-Users --description "Users who need S3 access"


(Note the id of the group from the output)

Add Your User to the Group:

oci iam group add-user \
    --user-id <your_user_ocid> \
    --group-id <group_id_from_previous_step>


Create the Policy:
A policy is just a text statement. We will grant the group S3-Users permission to manage all objects in all buckets in the tenancy.

oci iam policy create \
    --compartment-id <your_tenancy_ocid> \
    --name S3-User-Policy \
    --description "Allow S3-Users to manage all buckets and objects" \
    --statements '["Allow group S3-Users to manage object-family in tenancy"]'


Your user (and the S3 keys associated with them) now has full permission to list, read, and write objects.

Step 5: Putting It All Together (Boto3 Example)

You now have all 5 pieces of information needed to configure an S3 client:

Access Key ID: The id from Step 3 (e.g., aaaabbbbccccdddd1111)

Secret Access Key: The key from Step 3 (e.g., A1b2C/d3E+f4G/h5iJk6L+mN==)

Bucket Name: The name from Step 2 (e.g., my-s3-bucket)

Region: Your OCI region (e.g., us-ashburn-1)

Namespace: The string from Step 1C (e.g., my-namespace)

You use these to build the Endpoint URL:
https://<namespace>.compat.objectstorage.<region>.oraclecloud.com

Example Endpoint URL:
https://my-namespace.compat.objectstorage.us-ashburn-1.oraclecloud.com

Boto3 (Python) Uploader Script (uploader.py)

Here is a Python script configured to use these values to upload files.

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
# --- FILL IN YOUR VALUES ---
namespace = 'VALUE' # From Step 1C
region = 'ap-hyderabad-1' # Your OCI region
aws_access_key_id = 'VALUE' # From Step 3 ("id")
aws_secret_access_key = 'VALUE' # From Step 3 ("key")
bucket_name = 'VALUE' # From Step 2
# ---------------------------

s3 = boto3.client(
    service_name='s3',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    endpoint_url=f'https://{namespace}.compat.objectstorage.{region}.oraclecloud.com',
    region_name=region
)

# Set the folder path to upload
folder_path = '/content/3' # Example: '/path/to/your/files'

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
    Format: https://objectstorage.{region}[.oraclecloud.com/n/](https://.oraclecloud.com/n/){namespace}/b/{bucket}/o/{object}
    Note: Bucket must be public for these URLs to work
    """
    public_urls = []
    for file_name in file_names:
        # URL encode the file name to handle spaces and special characters
        encoded_name = quote(file_name, safe='')
        url = f"https://objectstorage.{region}[.oraclecloud.com/n/](https://.oraclecloud.com/n/){namespace}/b/{bucket_name}/o/{encoded_name}"
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
