# PSE84 M33: program raw flash, invalidate XIP caches, then verify XIP aliases.

proc m33_halt_all {} {
    set target cat1d.cm33
    catch {$target arp_examine}
    $target arp_halt
    if {![ifx::poll_halted $target 1000]} {
        error "cannot halt $target"
    }
}

proc m33_wait_clear {address mask label} {
    for {set i 0} {$i < 1000} {incr i} {
        set value [ifx::read32 cat1d.sys33 $address]
        if {($value & $mask) == 0} {
            return
        }
        sleep 1
    }
    error [format "%s timeout at 0x%08x" $label $address]
}

proc m33_invalidate_xip {} {
    targets cat1d.sys33
    ifx::write32 cat1d.sys33 0x42223008 0x3
    m33_wait_clear 0x42223008 0x3 "ICACHE0 invalidate"
}

proc m33_start_ns {} {
    targets cat1d.cm33
    if {![cat1d::reset_halt cm33_ns reset]} {
        error "cannot reach the Non-Secure reset handler"
    }
    if {[ifx::is_secure_domain cat1d.cm33]} {
        error "CM33 is still Secure at the Non-Secure reset handler"
    }
    set ctl [ifx::read32 cat1d.sys33 0x42223000]
    if {($ctl & 0x80000000) == 0} {
        error [format "ICACHE0 CA_EN is not set: 0x%08x" $ctl]
    }
    set cmd [ifx::read32 cat1d.sys33 0x42223008]
    if {($cmd & 0x3) != 0} {
        error [format "ICACHE0 CMD is not idle: 0x%08x" $cmd]
    }
}

proc m33_compare_alias {cached raw words} {
    for {set i 0} {$i < $words} {incr i} {
        set ca [expr {$cached + 4 * $i}]
        set ra [expr {$raw + 4 * $i}]
        set cv [ifx::read32 cat1d.sys33 $ca]
        set rv [ifx::read32 cat1d.sys33 $ra]
        if {$cv != $rv} {
            error [format "XIP mismatch 0x%08x=0x%08x, 0x%08x=0x%08x" $ca $cv $ra $rv]
        }
    }
}

proc m33_verified_flash {image xip_image standalone} {
    m33_halt_all
    m33_invalidate_xip

    targets cat1d.cm33
    reset init
    targets cat1d.cm33
    flash write_image erase $image 0 ihex
    flash verify_image $image 0 ihex

    m33_halt_all
    m33_invalidate_xip

    targets cat1d.sys33
    verify_image $xip_image 0 ihex
    m33_compare_alias 0x08377060 0x60377060 8
    m33_compare_alias 0x181042b8 0x701042b8 8

    targets cat1d.cm33
    reset init
    targets cat1d.cm33
    m33_start_ns

    if {$standalone} {
        targets cat1d.cm33
        resume
    }
}

if {![info exists M33_IMAGE] || ![info exists M33_XIP_IMAGE]} {
    error "M33_IMAGE and M33_XIP_IMAGE are required"
}
if {![info exists M33_STANDALONE]} {
    set M33_STANDALONE 0
}

if {[catch {
    init
    adapter speed 12000
    m33_verified_flash $M33_IMAGE $M33_XIP_IMAGE $M33_STANDALONE
} message]} {
    catch {m33_halt_all}
    puts stderr "M33 verified flash failed: $message"
    shutdown error
}

if {$M33_STANDALONE} {
    shutdown
}
