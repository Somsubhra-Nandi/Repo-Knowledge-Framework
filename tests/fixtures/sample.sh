#!/bin/bash

source ./utils.sh

get_user() {
    local id=$1
    format_user "$id"
}

format_user() {
    local id=$1
    echo "user:$id"
}

main() {
    local result
    result=$(get_user "123")
    echo "$result"
}

main "$@"
