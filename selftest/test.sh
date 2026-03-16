#!/bin/bash
# Copyright (c), 2023-2024, Huawei Tech. Co., Ltd.

testcase_is_successful="yes"
testcase_error_output_mode="console"
test_error_log_dir="./error_log/"

testcase_success=0
testcase_fail=0
testcase_timeout=0

success_cases=()
fail_cases=()
timeout_cases=()

# skip test cases
test_skip_status=222
current_arch=$(uname -m)
test_skip_cases=()

actual_skip_cases=()
actual_skip_nums=0

# timeout exit code
test_timeout_status=137

function read_skip_cases()
{
    file=$1
    while IFS= read -r line || [ -n "$line" ]; do
        # skip lines starting with '#'
        if [[ "$line" =~ ^# ]]; then
            continue
        fi
        # remove the blanks
        line=$(echo "$line" | xargs)
        # skip blank line
        if [[ -z "$line" ]]; then
            continue
        fi
        if [[ "$line" == *":"* ]]; then
            testcase=$(echo "$line" |cut -d':' -f1)
            arch=$(echo "$line" |cut -d':' -f2-)
            if [ $arch == $current_arch ]; then
                test_file=$(find ./ -type f \( -name "$testcase.sh" -o -name "$testcase.py" \))
                test_skip_cases+=("$test_file")
            fi
        else
            test_file=$(find ./ -type f \( -name "$line.sh" -o -name "$line.py" \))
            test_skip_cases+=("$test_file")
        fi

    done < $file
}

function get_file_name_without_extension()
{
    local file_path=$1
    # file name with extension
    local filename=$(basename "$file_path")
    # file name without extension
    local filename_no_ext="${filename%.*}"
    echo "$filename_no_ext"
}

function do_test_file()
{
    testfile="$1"
    if echo "${test_skip_cases[@]}" | grep -qw "$testfile"; then
        ((++actual_skip_nums))
        actual_skip_cases+=("$testfile")
        return $test_skip_status
    fi

    extension="${testfile##*.}"
    test_name="$(get_file_name_without_extension $testfile)"

    if [ "$extension" == "sh" ]; then
        dbus_output=$(systemctl start xalarmd 2>&1)
        ret=$?
        if [ $ret -eq 0 ]; then
            systemctl stop xalarmd
        fi
        if [[ "$dbus_output" == *"Failed to connect to bus: Host is down"* ]]; then
            ((++actual_skip_nums))
            actual_skip_cases+=("$testfile")
            return $test_skip_status
        fi
        timeout --signal=KILL 300s sh $testfile > "${test_name}.log" 2>&1
    elif [ "$extension" == "py" ]; then
        pytest-3 $testfile > "${test_name}.log" 2>&1
    fi
    ret=$?

    if [ $ret -eq 0 ]; then
        ((++testcase_success))
        success_cases+=("$testfile")
        rm -rf "${test_name}.log"
    elif [ $ret -eq $test_timeout_status ]; then
        testcase_is_successful="no"
        ((++testcase_timeout))
        timeout_cases+=("$testfile")
        if [ $testcase_error_output_mode == "console" ]; then
            cat "${test_name}.log"
            rm -rf "${test_name}.log"
        else
            mv "${test_name}.log" $test_error_log_dir"${test_name}.log"
        fi
    else
        testcase_is_successful="no"
        ((++testcase_fail))
        fail_cases+=("$testfile")
        if [ $testcase_error_output_mode == "console" ]; then
            cat "${test_name}.log"
            rm -rf "${test_name}.log"
        else
            mv "${test_name}.log" $test_error_log_dir"${test_name}.log"
        fi
    fi
    return $ret
}

function print_test_log_format()
{
    current_test_index=$1
    test_total_count=$2
    test_case_file=$3
    test_status_string=$4
    test_cost_time=$5
    if [ -n "$test_cost_time" ]; then
        printf "%3d/%-3d %-60s %7s  %.2fs\n" $current_test_index $test_total_count $(basename $test_case_file) $test_status_string $test_cost_time
    else
        printf "%3d/%-3d %-60s %7s\n" $current_test_index $test_total_count $(basename $test_case_file) $test_status_string
    fi
}

function output_test_result_detail()
{
    current_test_index=$1
    test_total_count=$2
    test_case_file=$3
    test_status_code=$4
    test_cost_time=$5
    if [ $test_status_code -eq 0 ]; then
        print_test_log_format $current_test_index $test_total_count $test_case_file "SUCCESS" $test_cost_time
    elif [ $test_status_code -eq 137 ]; then
        print_test_log_format $current_test_index $test_total_count $test_case_file "TIMEOUT" $test_cost_time
    elif [ $test_status_code -eq $test_skip_status ]; then
        print_test_log_format $current_test_index $test_total_count $test_case_file "SKIPPED" $test_cost_time
    else
        print_test_log_format $current_test_index $test_total_count $test_case_file " ERROR " $test_cost_time
    fi
}

function do_all_test()
{
    test_count=0
    test_files=$(find test/ -type f \( -name "test_*.sh" -o -name "test_*.py" \))
    test_total_count=$(echo "$test_files" | wc -l)
    for testfile in $test_files
    do
        test_count=$((test_count+1))
        print_test_log_format $test_count $test_total_count $testfile "RUNNING"

        start_time_tmp=$(date +%s)
        do_test_file $testfile
        ret=$?
        end_time_tmp=$(date +%s)

        # move the cursor to the previous line
        echo -en "\033[1A\033[K"
        output_test_result_detail $test_count $test_total_count $testfile $ret $((end_time_tmp - start_time_tmp))
    done

}

function do_one_test()
{
    testfile=$1

    print_test_log_format 1 1 $testfile "RUNNING"
    
    start_time_tmp=$(date +%s)
    do_test_file $testfile
    ret=$?
    end_time_tmp=$(date +%s)

    # move the cursor to the previous line
    echo -en "\033[1A\033[K"
    output_test_result_detail 1 1 $testfile $ret $((end_time_tmp - start_time_tmp))
}

function output_unsuccessful_test_cases()
{
    if [ $testcase_fail -gt 0 ]; then
        printf "============== FAILED TEST ==============\n"
        for file_name in "${fail_cases[@]}"; do
            printf "$(basename $file_name)\n"
        done
    fi

    if [ $testcase_timeout -gt 0 ]; then
        printf "============== TIMEOUT TEST ==============\n"
        for file_name in "${timeout_cases[@]}"; do
            printf "$(basename $file_name)\n"
	done
    fi

    if [ $actual_skip_nums -gt 0 ]; then
        printf "============== SKIPPED TEST ==============\n"
        for file_name in "${actual_skip_cases[@]}"; do
             printf "$(basename $file_name)\n"
	done
    fi
}

function output_test_cases_result()
{
    printf "============== TEST RESULT ==============\n"
    printf "success:         $testcase_success\n"
    printf "skipped:         $actual_skip_nums\n"
    printf "timeout:         $testcase_timeout\n"
    printf "failed:          $testcase_fail\n"
    printf "total duration:  ${total_time}s\n"
    printf "=============== TEST END ================\n"
}

function do_test()
{
    if [ "$2" == "file" ]; then
        testcase_error_output_mode="file"
	    if [ ! -d "${test_error_log_dir}" ];then
	        mkdir ${test_error_log_dir}
	    fi
    fi

    # read whitelist
    read_skip_cases "testsuite_skip_list"

    if [ "$1" == "all" ] || [ $# -eq 0 ]; then
        # start to test
        start_time=$(date +%s)
        do_all_test
        end_time=$(date +%s)
        total_time=$((end_time - start_time))

        # print test result info
        output_unsuccessful_test_cases
        output_test_cases_result
    else
        test_file=$(find ./ -type f \( -name "$1.sh" -o -name "$1.py" \))
        if [ ! -f "$test_file" ]; then
            printf "testsuite $1 not exist, check whether the testname is corrent, we need to use $1 to match test/$1.py or test/$1.sh\n"
            exit 1
        else
            do_one_test $test_file
        fi
    fi

    # remove .pyc file
    find . -name "*.pyc" | xargs rm -rf

    if [ "$testcase_is_successful" == "no" ]; then
        printf "test failed!!!\n"
        if [ $testcase_error_output_mode == "file" ]; then
            printf "=============== ERROR INFO ==============\n"
            printf "the execution log of the failed case refers to the following file:\n"
            for file in "$test_error_log_dir"*; do
                if [ -f "$file" ]; then
                    printf "%s\n" $file
                fi
            done
            printf "=============== ERROR END ===============\n" 
        fi
        exit 1
    fi
}

do_test $1 $2
