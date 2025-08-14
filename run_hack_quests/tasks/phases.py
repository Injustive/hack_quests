from utils.client import Client
from utils.utils import (retry, check_res_status, get_utc_now,
                         get_data_lines, sleep, Logger,
                         read_json, Contract, generate_random_hex_string,
                         get_utc_now, approve_asset, asset_balance, get_decimals, approve_if_insufficient_allowance,
                         generate_random, retry_js, JSException, ModernTask, get_session, get_gas_params, estimate_gas)


class Phases:
    def __init__(self, session, client, db_manager, logger):
        self.session = session
        self.client = client
        self.db_manager = db_manager
        self.logger = logger

    @retry()
    @check_res_status()
    async def submit_quiz(self, quiz_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation SubmitQuiz($input: SubmitQuizInput!) {\n  submitQuiz(input: $input) {\n    treasure {\n      exp\n      coin\n    }\n  }\n}\n    ',
            'variables': {
                'input': {
                    'lessonId': quiz_id,
                    'status': True,
                    'quizIndex': 0,
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def complete_quiz(self, quiz_id, course_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    mutation CompleteLesson($input: CompleteLessonInput!) {\n  completeLesson(input: $input) {\n    nextLearningInfo {\n      learningId\n      id\n      type\n      alias\n    }\n  }\n}\n    ',
            'variables': {
                'input': {
                    'lessonId': quiz_id,
                    'courseId': course_id,
                    'completeCourse': False,
                    'phaseId': '',
                    'lang': 'en',
                },
            },
        }
        return await self.session.post(url, json=json_data)

    async def complete_unit(self):
        all_courses = (await self.get_all_courses()).json()['data']['ecosystem']
        current_phase = all_courses['currentPhase']['title']
        for phase in all_courses['phases']:
            if phase['title'] == current_phase:
                for course in phase['courses']:
                    units = (await self.find_course_unit(course['id'])).json()['data']['findCourseDetail']['units']
                    for unit in units:
                        pages = unit['pages']
                        if all(page['isCompleted'] for page in pages):
                            self.logger.success(f'Unit {unit["title"]} already completed!')
                            continue
                        for page in pages:
                            if page['isCompleted']:
                                self.logger.info(f"Quiz {page['title']} already completed!")
                                continue
                            self.logger.info(f"Starting completing quiz {page['title']}...")
                            await self.submit_quiz(page['id'])
                            await sleep(3, 5)
                            await self.complete_quiz(page['id'], 'd927cdac-7fcb-4516-abab-624af8e44894')
                        else:
                            self.logger.success(f'Unit {unit["title"]} completed successfully!')
                            return

    @retry()
    @check_res_status()
    async def find_course_unit(self, course_id):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    query FindCourseUnits($where: CourseV2WhereInput) {\n  findCourseDetail(where: $where) {\n    units {\n      title\n      description\n      progress\n      pages {\n        id\n        title\n        isCompleted\n      }\n    }\n    alias\n    id\n    currentPageId\n    nextPageId\n  }\n}\n    ',
            'variables': {
                'where': {
                    'id': {
                        'equals': course_id,
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def get_all_courses(self):
        url = 'https://api.hackquest.io/graphql'
        json_data = {
            'query': '\n    query FindActiveEcosystemInfo($where: EcosystemInfoWhereUniqueInput!) {\n  ecosystem: findUniqueEcosystemInfo(where: $where) {\n    ecosystemId\n    lang\n    basic {\n      type\n      image\n    }\n    phases {\n      id\n      coin\n      title\n      progress\n      order\n      cover\n      certificateId\n      certificate {\n        id\n        image\n        name\n        template\n        chainId\n        contract\n        credits\n        extra\n        userCertification {\n          claimed\n          mint\n          username\n          certificateId\n          certificationId\n        }\n      }\n      rewardClaimRecord {\n        claimed\n        coin\n      }\n      courses {\n        id\n        alias\n        type\n        title\n        icon\n        progress\n        order\n        currentPageId\n        units {\n          id\n          currentPageId\n          title\n          progress\n          isCompleted\n        }\n      }\n      quizzes {\n        id\n        order\n        progress\n        currentPageId\n        extra\n        quizList {\n          id\n          correct\n        }\n        description\n      }\n      extra\n      build {\n        hackathons {\n          id\n          name\n          alias\n          status\n          currentStatus\n          info {\n            image\n            intro\n          }\n          timeline {\n            timeZone\n            openReviewSame\n            registrationOpen\n            registrationClose\n            submissionOpen\n            submissionClose\n            rewardTime\n          }\n        }\n      }\n    }\n    currentPhase {\n      id\n      title\n      learningInfo {\n        id\n        alias\n        type\n        learningId\n      }\n    }\n  }\n}\n    ',
            'variables': {
                'where': {
                    'ecosystemId_lang': {
                        'ecosystemId': 'b950a72f-3fdf-4581-8ddb-3a3d1630044d',
                        'lang': 'en',
                    },
                },
            },
        }
        return await self.session.post(url, json=json_data)
