import argparse
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Max, Min
from rental.models import HouseTS

# TODO: uniq support postgres only

def parse_date(date_str):
    try:
        return timezone.make_aware(datetime.strptime(date_str, '%Y%m%d'))
    except ValueError:
        raise argparse.ArgumentTypeError('Invalid date string: {}'.format(date_str))

class Command(BaseCommand):
    help = 'Validate whether there are invalid data generated by data provider'
    requires_migrations_checks = True

    # must not change
    should_be_static_fields = [
        'top_region',
        'sub_region',
        'vendor',
        'building_type',
        'property_type',
    ]

    # must not change too many times
    should_be_stable_fiedls = [
        'n_living_room',
        'n_bed_room',
        'n_bath_room',
        'n_balcony',
        'deposit_type',
        'n_month_deposit',
        'monthly_management_fee',
        'has_parking',
        'is_require_parking_fee',
        'monthly_parking_fee',
        'rough_address',
        'has_tenant_restriction',
        'has_gender_restriction',
        'gender_restriction',
        'can_cook',
        'allow_pet',
        'has_perperty_restration',
        'contact',
    ]

    should_be_small_diff_fields = [
        'deposit',
        'monthly_price',
        'floor',
        'total_floor',
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            '-f',
            '--from',
            dest='from_date',
            required=True,
            type=parse_date,
            help='from date, format: YYYYMMDD, default today'
        )

        parser.add_argument(
            '-t',
            '--to',
            dest='to_date',
            required=True,
            type=parse_date,
            help='to date, format: YYYYMMDD, default today'
        )

    def handle(self, *args, **options):
        from_date = options['from_date']
        to_date = options['to_date']

        static_qs = HouseTS.objects.filter(
            created__gte=from_date,
            created__lte=to_date,
        ).exclude(
            rough_address__isnull=True,
        ).values(
            'vendor_house_id',
            *self.should_be_static_fields
        ).annotate(
            count=Count('id'),
        ).order_by(
            'vendor_house_id'
        )

        static_houses = {}
        total_houses = 0
        total_invalid_houses = 0
        for house in static_qs:
            house_id = house['vendor_house_id']
            # print('  {} x {} - {}'.format(house_id, house['count'], house['building_type']))
            if house['vendor_house_id'] in static_houses:
                static_houses[house_id].append(house['count'])
                total_houses += 1
            else:
                static_houses[house_id] = [house['count']]
                total_invalid_houses += 1

        for house_id in static_houses:
            if len(static_houses[house_id]) > 1:
                print('[STATIC] House {} changed {} ({}) times!!'.format(house_id, len(static_houses[house_id]), static_houses[house_id]))

        print('[STATIC] Invald house: {}/{}'.format(total_invalid_houses, total_houses))

        # min should be bigger than max/2
        annotates = {}

        for field in self.should_be_small_diff_fields:
            annotates['max_{}'.format(field)] = Max(field)
            annotates['min_{}'.format(field)] = Min(field)

        small_diff_qs = HouseTS.objects.filter(
            created__gte=from_date,
            created__lte=to_date,
        ).exclude(
            rough_address__isnull=True,
        ).values(
            'vendor_house_id',
        ).annotate(
            count=Count('id'),
            **annotates,
        ).order_by(
            'vendor_house_id'
        )

        total_houses = 0
        total_invalid_houses = 0
        for house in small_diff_qs:
            is_invalid = False
            total_houses += 1

            for field in self.should_be_small_diff_fields:
                max_value = house['max_{}'.format(field)]
                min_value = house['min_{}'.format(field)]
                if max_value is not None and min_value is not None and max_value / 2 > min_value:
                    is_invalid = True
                    print('[SMALL] House {} field {} change too much, from {} to {}'.format(
                        house['vendor_house_id'], field, min_value, max_value
                    ))

            if is_invalid:
                total_invalid_houses += 1

        print('[SMALL] Invald house: {}/{}'.format(total_invalid_houses, total_houses))
