Using OCI Object Storage with S3-Compatible APIs via the CLIOracle Cloud Infrastructure (OCI) provides an S3-compatible API for its Object Storage service. This allows you to use S3-compatible tools, like boto3, with your OCI buckets.This guide covers the complete end-to-end process using the OCI CLI.PrerequisitesOCI Account: You must have an Oracle Cloud account.OCI CLI: The OCI Command Line Interface must be installed and configured.If you are using the OCI Cloud Shell, the CLI is pre-configured.For a local setup, see the OCI CLI Installation Guide.OCI to S3: Understanding the "Where to Find What"Before you begin, it's crucial to understand how OCI's terms map to standard S3 terms:S3 (AWS) TermOCI (Oracle) TermHow to Find It (via OCI CLI)Bucket NameBucket NameYou create this. Must be unique in your namespace.AWS Access Key IDCustomer Secret Key (Access Key)You generate this. It's the id in the output.AWS Secret KeyCustomer Secret Key (Secret Key)You generate this. It's the key in the output.AWS RegionOCI Regione.g., us-ashburn-1, eu-frankfurt-1S3 EndpointS3-Compatible Endpointhttps://<namespace>.compat.objectstorage.<region>.oraclecloud.comYou will need to find three key pieces of information:Your Tenancy (Root Compartment) OCID: Where you'll create the bucket (for simplicity).Your User OCID: The user who will "own" the S3 keys.Your Object Storage Namespace: This is critical for the S3 endpoint URL.Step 1: Find Your Core Information (Tenancy, User, Namespace)Run these commands in your OCI CLI (Cloud Shell recommended) to gather the IDs you'll need.A. Find Your Tenancy (Root Compartment) OCIDThis is the OCID for your main root compartment (e.g., my-root-compartment (root)).If in OCI Cloud Shell (Easiest Method):curl -H "Authorization: Bearer Oracle" -L [http://169.254.169.254/opc/v1/instance/compartmentId](http://169.254.169.254/opc/v1/instance/compartmentId)
If on a Local CLI:cat ~/.oci/config | grep tenancy
You will get a line like tenancy=ocid1.tenancy.oc1..aaaa.... Copy the OCID.B. Find Your User OCIDThis command gets the OCID of the currently authenticated user.oci session user get --query "data.id" --raw-output
C. Find Your Object Storage NamespaceThis is a unique string for your tenancy (e.g., my-namespace).oci os ns get --query "data" --raw-output
Save these three values. You'll need them for the next steps and for your S3-compatible application.Step 2: Create Your BucketUse the oci os bucket create command. For simplicity, we will create this in your root compartment (Tenancy).Replace <your_tenancy_ocid> with the ID from Step 1A.Replace <your_unique_bucket_name> with your desired bucket name (e.g., my-s3-bucket).oci os bucket create \
    --compartment-id <your_tenancy_ocid> \
    --name <your_unique_bucket_name>
Example:oci os bucket create \
    --compartment-id ocid1.tenancy.oc1..aaaa... \
    --name my-s3-bucket
If successful, you will see a JSON output confirming the bucket is created.Step 3: Generate S3-Compatible KeysNow, create the S3-compatible Access Key and Secret Key, which OCI calls a "Customer Secret Key".Replace <your_user_ocid> with the ID from Step 1B.Replace <key_display_name> with a memorable name for the key.oci iam customer-secret-key create \
    --user-id <your_user_ocid> \
    --display-name <key_display_name>
Example:oci iam customer-secret-key create \
    --user-id ocid1.user.oc1..aaaa... \
    --display-name "my-s3-app-key"
⚠️ IMPORTANT: SAVE YOUR KEYSThe CLI will output a JSON block. This is the only time you will ever see the secret key.{
  "data": {
    "display-name": "my-s3-app-key",
    "id": "aaaabbbbccccdddd1111",            <-- THIS IS YOUR S3 ACCESS KEY ID
    "key": "A1b2C/d3E+f4G/h5iJk6L+mN==",  <-- THIS IS YOUR S3 SECRET ACCESS KEY
    "lifecycle-state": "ACTIVE",
    "time-created": "2025-10-23T08:15:00.123+00:00",
    "user-id": "ocid1.user.oc1..aaaa..."
  }
}
Save the id and key values in a secure password manager immediately.Step 4: Providing Permissions (OCI IAM Policy)By default, the new S3 keys can only do what the user they are tied to (the user from Step 1B) can do. For your S3 tool to read and write to buckets, that user must have Object Storage permissions.If you are the tenancy administrator, you likely already have a policy like Allow group Administrators to manage all-resources in tenancy, which is why your bucket creation worked.For a non-admin user, you must create a policy to grant them access. The best practice is to create a group, add the user to the group, and create a policy for that group.Example: Granting a group access to all buckets in the tenancyCreate a Group:oci iam group create --name S3-Users --description "Users who need S3 access"
(Note the id of the group from the output)Add Your User to the Group:oci iam group add-user \
    --user-id <your_user_ocid> \
    --group-id <group_id_from_previous_step>
Create the Policy:A policy is just a text statement. We will grant the group S3-Users permission to manage all objects in all buckets in the tenancy.oci iam policy create \
    --compartment-id <your_tenancy_ocid> \
    --name S3-User-Policy \
    --description "Allow S3-Users to manage all buckets and objects" \
    --statements '["Allow group S3-Users to manage object-family in tenancy"]'
Your user (and the S3 keys associated with them) now has full permission to list, read, and write objects.Step 5: Putting It All Together (Boto3 Example)You now have all 5 pieces of information needed to configure an S3 client:Access Key ID: The id from Step 3 (e.g., aaaabbbbccccdddd1111)Secret Access Key: The key from Step 3 (e.g., A1b2C/d3E+f4G/h5iJk6L+mN==)Bucket Name: The name from Step 2 (e.g., my-s3-bucket)Region: Your OCI region (e.g., us-ashburn-1)Namespace: The string from Step 1C (e.g., my-namespace)You use these to build the Endpoint URL:https://<namespace>.compat.objectstorage.<region>.oraclecloud.comExample Endpoint URL:https://my-namespace.compat.objectstorage.us-ashburn-1.oraclecloud.comBoto3 (Python) Example (example.py)Here is a Python script configured with these values.import boto3
import os
from botocore.exceptions import ClientError

# === CONFIGURATION ===
OCI_ACCESS_KEY_ID = "YOUR_S3_ACCESS_KEY_ID"  # From Step 3
OCI_SECRET_ACCESS_KEY = "YOUR_S3_SECRET_KEY" # From Step 3
OCI_ENDPOINT_URL = "https://<your_namespace>.compat.objectstorage.<your_region>.oraclecloud.com"
OCI_REGION = "<your_region>"
BUCKET_NAME = "<your_bucket_name>"
FILE_TO_UPLOAD = "/path/to/your/test.txt" # Make sure this file exists
OBJECT_NAME = "my-test-file.txt" # The name it will have in the bucket

# Initialize S3 client for OCI
s3 = boto3.client(
    service_name='s3',
    aws_access_key_id=OCI_ACCESS_KEY_ID,
    aws_secret_access_key=OCI_SECRET_ACCESS_KEY,
    endpoint_url=OCI_ENDPOINT_URL,
    region_name=OCI_REGION
)

# --- 1. Upload a file ---
try:
    file_size = os.path.getsize(FILE_TO_UPLOAD)
    print(f"Uploading {FILE_TO_UPLOAD} to {BUCKET_NAME} as {OBJECT_NAME}...")
    
    with open(FILE_TO_UPLOAD, 'rb') as f:
        s3.put_object(
            Body=f,
            Bucket=BUCKET_NAME,
            Key=OBJECT_NAME,
            ContentLength=file_size # This is critical for OCI
        )
    print(f"✓ Successfully uploaded {OBJECT_NAME}\n")

    # --- 2. Generate a Presigned URL ---
    print(f"Generating presigned URL for {OBJECT_NAME} (valid for 1 hour)...")
    url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': OBJECT_NAME},
        ExpiresIn=3600  # 1 hour
    )
    print(f"URL:\n{url}\n")

except ClientError as e:
    print(f"\n✗ Error: {e}\n")
except FileNotFoundError:
    print(f"\n✗ Error: File not found at {FILE_TO_UPLOAD}")
