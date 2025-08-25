#!./test/libs/bats/bin/bats

load 'libs/bats-support/load'
load 'libs/bats-assert/load'


setup() {
    if [ -f ./filelist.txt ]; then
        rm ./filelist.txt
    fi
    if [ -f ./prepare_data.conf ]; then
        rm ./prepare_data.conf
    fi
    if [ -d $BATS_TMPDIR/tmp-output ]; then
        rm -rf $BATS_TMPDIR/tmp-output
    fi
}

teardown() {
    if [ -f ./filelist.txt ]; then
        rm ./filelist.txt
    fi
    if [ -f ./prepare_data.conf ]; then
        rm ./prepare_data.conf
    fi
    if [ -d $BATS_TMPDIR/tmp-output ]; then
        rm -rf $BATS_TMPDIR/tmp-output
    fi
}

@test "Test no prepare_data.conf file present fails" {
    run ./prepare_data.sh
    assert_failure
    assert_line "./prepare_data.conf is required but was not found"
}

@test "Test no filelist present fails" {
    cp ./prepare_data.conf.example ./prepare_data.conf
    source ./prepare_data.conf
    run ./prepare_data.sh
    assert_failure
    assert_line "$FILELIST is required"
}

@test "Test display help" {
    touch ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    run ./prepare_data.sh --help
    assert_failure
    assert_line "usage: ./prepare_data.sh [target_dir|--dry-run]"
    run ./prepare_data.sh -h
    assert_failure
    assert_line "usage: ./prepare_data.sh [target_dir|--dry-run]"
    run ./prepare_data.sh
    assert_failure
    assert_line "usage: ./prepare_data.sh [target_dir|--dry-run]"
    run ./prepare_data.sh a b
    assert_failure
    assert_line "usage: ./prepare_data.sh [target_dir|--dry-run]"
}

@test "Empty filelist dry-run MD5check fails" {
    touch ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    run ./prepare_data.sh --dry-run
    assert_failure
}

@test "Empty filelist dry-run file exists passes" {
    touch ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    sed 's/true/false/g' ./prepare_data.conf > ./prepare_data.tmp && mv ./prepare_data.tmp ./prepare_data.conf
    cat ./prepare_data.conf
    run ./prepare_data.sh --dry-run
    assert_success
}

@test "MD5 filelist dry-run MD5check passes" {
    cp ./test/resources/filelist_md5.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    run ./prepare_data.sh --dry-run
    assert_success
}

@test "MD5 filelist dry-run file exists passes" {
    cp ./test/resources/filelist_md5.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    sed 's/true/false/g' ./prepare_data.conf > ./prepare_data.tmp && mv ./prepare_data.tmp ./prepare_data.conf
    run ./prepare_data.sh --dry-run
    assert_success
}

@test "Normal filelist dry-run MD5check fails" {
    cp ./test/resources/filelist.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    run ./prepare_data.sh --dry-run
    assert_failure
}

@test "Normal filelist dry-run file exists passes" {
    cp ./test/resources/filelist.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    sed 's/true/false/g' ./prepare_data.conf > ./prepare_data.tmp && mv ./prepare_data.tmp ./prepare_data.conf
    run ./prepare_data.sh --dry-run
    assert_success
}

@test "Copy if output dir does not exist fails" {
    cp ./test/resources/filelist.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    run ./prepare_data.sh $BATS_TMPDIR/tmp-output
    assert_failure
    cp ./test/resources/filelist_md5.txt ./filelist.txt
    run ./prepare_data.sh $BATS_TMPDIR/tmp-output
    assert_failure
}

@test "MD5 filelist copy passes" {
    cp ./test/resources/filelist_md5.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    mkdir $BATS_TMPDIR/tmp-output
    ./prepare_data.sh $BATS_TMPDIR/tmp-output
    assert_success
    FILELIST=`realpath ./filelist.txt`
    cd $BATS_TMPDIR/tmp-output
    ls -lah "$BATS_TMPDIR/tmp-output"
    md5sum -c $FILELIST
    assert_success
}

@test "Normal filelist copy passes" {
    cp ./test/resources/filelist.txt ./filelist.txt
    cp ./prepare_data.conf.example ./prepare_data.conf
    mkdir $BATS_TMPDIR/tmp-output
    run ./prepare_data.sh $BATS_TMPDIR/tmp-output
    assert_success
    FILELIST=`realpath ./filelist.txt`
    cd $BATS_TMPDIR/tmp-output
    ! (for i in `awk -F " " '{print $NF}' $FILELIST`; do test ! -f "$i" && echo "$i does not exist" && test -f "$i"; done | grep "not")
    assert_success
}

@test "Empty filelist copy passes" {
    touch ./filelist.txt
    mkdir $BATS_TMPDIR/tmp-output
    cp ./prepare_data.conf.example ./prepare_data.conf
    run ./prepare_data.sh $BATS_TMPDIR/tmp-output
    assert_success
}
