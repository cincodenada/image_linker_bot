#!/usr/bin/perl
use Date::Parse;
use Path::Class;

$suffix = shift(@ARGV);

$comments = Path::Class::File->new("comments_$suffix.tsv")->openw();
$candidates = Path::Class::File->new("candidates_$suffix.tsv")->openw();

$mode = '';
while(<>) {
    if(/^(201\S+ \S+)/) {
        $lastdate = $1;
        $lastts = str2time($lastdate);
        $mode = 'dateline';
    }

    if(/^Possible new image for .*\/(\w+)$/) {
        $mode = 'newimage';
        $commentid = $1;
    } elsif($mode eq 'newimage') {
        if($_) {
            if(/(\S+) (\S+)$/) {
                $candidates->print(join("\t", $commentid, $1, $2, $lastts) . "\n");
                $mode = '';
            }
        }
    }

    if(/Commenting on .*\/(?<cid>\w+) \((?<image>.*)\)$/) {
        $comments->print(join("\t", $+{cid}, $+{image}, $lastts) . "\n");
    }
}
