terraform {
  backend "s3" {
    bucket         = "cpip-terraform-state-REPLACE_WITH_ACCOUNT_ID"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "cpip-terraform-locks"
    encrypt        = true
  }
}
