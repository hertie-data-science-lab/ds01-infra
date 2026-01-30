#!/bin/bash

# 1. Identify the inactive directories and save to a temporary list
echo "Searching for inactive student directories (no changes in 180 days)..."

targets=$(sudo find /home -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9][0-9][0-9]@hertie-school.lan' | while read dir; do
    recent=$(sudo find "$dir" -type f -mtime -180 2>/dev/null | head -1)
    if [ -z "$recent" ]; then
        echo "$dir"
    fi
done)

# 2. Check if we found anything
if [ -z "$targets" ]; then
    echo "No inactive directories found. Nothing to delete."
    exit 0
fi

# 3. Show the user what is about to be deleted
echo "The following directories are INACTIVE and will be DELETED:"
echo "--------------------------------------------------------"
echo "$targets"
echo "--------------------------------------------------------"

# 4. Final confirmation
read -p "Delete these directories? (y/n): " confirm
if [ "$confirm" == "y" ]; then
    for dir in $targets; do
        echo "Deleting $dir..."
        sudo rm -rf "$dir"
    done
    echo "Cleanup complete."
else
    echo "Deletion cancelled."
fi