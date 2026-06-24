#!/bin/bash
# EC2 user-data (cloud-init) — installs Docker on first boot. Amazon Linux 2023.
dnf update -y
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user
